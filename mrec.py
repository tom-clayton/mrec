#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  mrec.py
#  
#  Copyright 2019 tom clayton
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
# alsa_output.pci-0000_00_1b.0.analog-stereo.monitor
# bluez_sink.53_6F_AA_57_FB_A0.a2dp_sink.monitor

import gi 
gi.require_version('Playerctl', '2.0')

from gi.repository import Playerctl, GLib
import sys
import threading
import subprocess
import os
import queue


music_root = "/home/tom/Music"    
capture_mutex = threading.Lock()
encode_queue = queue.Queue(5)

class Track:
    def __init__(self):
        self.data = bytearray()
        self.trackid = None

    def get_details(self, metadata):
        self.title = metadata['xesam:title']
        self.artist = ', '.join(metadata['xesam:artist'])
        self.album = metadata['xesam:album']
        self.albumartist = ', '.join(metadata['xesam:albumArtist'])
        self.track_number = metadata['xesam:trackNumber']
        self.trackid = metadata['mpris:trackid']
        
        # check for / in names. seperate function

        self.path = get_path(metadata)
        self.filename = get_filename(metadata)

        if os.path.exists(os.path.join(self.path, self.filename)):
            self.file_exists = True
            print(f"\n'{self.title}'  already exists\n")
            
        else:
            self.file_exists = False
            print(f"\nRecording: '{self.title}'\n")
            self.make_directories()
    
    def __del__(self):
        try:
            print (f"'{self.title}' data deleted") 
        except AttributeError:
            pass
            
    def make_directories(self):
        albumartist_dir = os.path.join(music_root, self.albumartist)
        if not os.path.exists(albumartist_dir):
            os.mkdir(albumartist_dir)
            
        album_dir = os.path.join(albumartist_dir, self.album)
        if not os.path.exists(album_dir):
            os.mkdir(album_dir)
            
    def encode(self):
        subprocess.run(["oggenc", "-r", 
                        "-q", "6",
                        "-a", self.artist,
                        "-t", self.title,
                        "-l", self.album,
                        "-o", os.path.join(self.path, self.filename),
                        "-"],
                        input=self.data)
            
def capture_input(recording_data):
    while True:
        if recording_data['is_playing']:
            capture_mutex.acquire()
            recording_data['recording'].data.extend(sys.stdin.buffer.read(4000))
            capture_mutex.release()
        else:
            sys.stdin.buffer.read(4000)

def encode_output():
    while True:
        track = encode_queue.get()
        track.make_directories()
        track.encode()
        encode_queue.task_done()
        del(track)

    # check for / in names. seperate function:

def get_path(metadata):
    return "{}/{}/{}".format(music_root,
                             ", ".join(metadata['xesam:albumArtist']),
                             metadata['xesam:album'])

def get_filename(metadata):
    return "{}{} {} - {}.ogg".format(
                "0" if int(metadata['xesam:trackNumber']) < 10 else "",
                metadata['xesam:trackNumber'],
                metadata['xesam:title'],
                ", ".join(metadata['xesam:artist']))
    

def on_status(player, status, recording_data):
    recording_data['is_playing'] = True if status.value_name == \
                                "PLAYERCTL_PLAYBACK_STATUS_PLAYING" \
                                else False

                      
def on_metadata(player, metadata, recording_data):
    prev_track = recording_data['recording']
    trackid = metadata['mpris:trackid']

    if prev_track.trackid != trackid: # track has changed.
        # start recording new track:
        capture_mutex.acquire()
        recording_data['recording'] = Track()
        capture_mutex.release()
        recording_data['recording'].get_details(metadata)

        # encode finished track:
        try:
            if not prev_track.file_exists:
                encode_queue.put(prev_track)
        except AttributeError:
            pass   
            
def main(args):
    if len(args) > 1 and os.path.exists(args[1]):
        global music_root
        music_root = args[1]
   
    player = Playerctl.Player() 
    player_name = player.get_property('player-name')
    if player_name:
        print(f"Found player: {player_name}")
    else:
        print("No player found, exiting")
        return -1

    recording_data = {'is_playing': None,   # get playing status in func call below
                      'recording': Track()} # initial dummy track to send data to 
    
    on_status(player, player.get_property('playback-status'), recording_data)

    # callbacks:
    player.connect('metadata', on_metadata, recording_data)
    player.connect('playback-status', on_status, recording_data)

    # threads:
    capture_thread = threading.Thread(target=capture_input, 
                                      args = (recording_data,),
                                      daemon = True)
                                      
    encode_thread = threading.Thread(target=encode_output, 
                                      daemon = True)                        
    capture_thread.start()
    encode_thread.start()

    main = GLib.MainLoop()
    main.run()
    
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
