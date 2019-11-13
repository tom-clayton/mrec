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
import time
import threading
import subprocess
import os
import queue
import logging

logging.basicConfig(level=logging.DEBUG,
                    filename='/home/tom/mrec.log',
                    filemode='a',
                    format='%(asctime)s - %(message)s')

music_root = "/home/tom/Music"
backup_dir = None
capture_mutex = threading.Lock()
encode_queue = queue.Queue(5)

class Track:
    def __init__(self):
        self.data = bytearray()
        self.trackid = None

    def get_details(self, metadata):
        self.title = metadata['xesam:title'].replace('/', ' ')
        self.artist = ', '.join(metadata['xesam:artist']).replace('/', ' ')
        self.album = metadata['xesam:album'].replace('/', ' ')
        self.albumartist = ', '.join(metadata['xesam:albumArtist'])\
                               .replace('/', ' ')
        self.track_number = "0" + str(metadata['xesam:trackNumber']) \
                            if metadata['xesam:trackNumber'] < 10 \
                            else str(metadata['xesam:trackNumber'])

        self.trackid = metadata['mpris:trackid']

        self.album_path = os.path.join(self.albumartist, self.album)
        self.filename = f"{self.track_number}{self.title} - {self.artist}.ogg"
        self.filepath = os.path.join(self.album_path, self.filename)
        
        if os.path.exists(os.path.join(music_root, self.filepath)):
            self.file_exists = True
            
            logging.info(f"'{self.title}'  already exists")
        else:
            self.file_exists = False
            logging.info(f"Recording: '{self.title}'")
    
    def __del__(self):
        try:
            logging.info(f"'{self.title}' data deleted") 
        except AttributeError:
            pass
            
    def make_directories(self, root):
        artist_path = os.path.join(root, self.albumartist)
        if not os.path.exists(artist_path):
            os.mkdir(artist_path)

        album_path = os.path.join(artist_path, self.album)   
        if not os.path.exists(album_path):
            os.mkdir(album_path)
            
    def encode(self):
        self.make_directories(music_root)
        subprocess.run(["oggenc", "-r", 
                        "-q", "6",
                        "-a", self.artist,
                        "-t", self.title,
                        "-l", self.album,
                        "-o", os.path.join(music_root, self.filepath),
                        "-"],
                        input=self.data)

    def backup(self):
        self.make_directories(backup_dir)
        subprocess.run(["cp",
                        os.path.join(music_root, self.filepath),
                        os.path.join(backup_dir, self.filepath)])
            

          
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
        track.encode()
        if backup_dir:
            track.backup()
        encode_queue.task_done()
        del(track)

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

    player_name = None
    while not player_name:
        player = Playerctl.Player() 
        player_name = player.get_property('player-name')
        time.sleep(5)
    
    logging.info(f"Mrec started, {player_name} found")

    recording_data = {'is_playing': False,  # track is playing 
                      'recording': Track()} # track object to send data to 
    
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
