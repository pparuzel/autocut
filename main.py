#!/usr/bin/env python3.7

import sys
import os
import math
import tempfile
import subprocess as sub

from datetime import timedelta


def get_time_and_levels(probe_process):
    for line in probe_process.stdout:
        yield map(float, line.decode().strip().split(','))


class AudioClipSlicer:
    def __init__(self, input_file, output_base_name=None):
        self.input_file = input_file
        input_base, extension = os.path.splitext(self.input_file)
        self.output_base_name = output_base_name if output_base_name else input_base
        self.extension = extension

    def run_montage(self, threshold):
        segments = self._analyze_audio_levels(self.input_file, threshold)
        if not segments:
            print(f'warning: no cuts received')
            return
        if math.log(len(segments), 10) > 3:
            print(f'error: too many segments')
            sys.exit(1)
        temp_dir = tempfile.mkdtemp(prefix=f'{self.output_base_name}_clips_', dir=os.getcwd())
        for i, (start, end) in enumerate(segments):
            self._slice_and_copy(start, end, output_file=os.path.join(temp_dir, f'{self.output_base_name}.{i+1:03}{self.extension}'))
        try:
            os.rmdir(temp_dir)
        except:
            pass

    def _slice_and_copy(self, start, end, output_file):
        args = [
            'ffmpeg',
            '-i',
            self.input_file,
            '-c',
            'copy',
            '-ss',
            f'{timedelta(seconds=start)}',
            '-to',
            f'{timedelta(seconds=end)}',
            output_file
        ]

        # print(f'slice-and-copy: {args}')
        # return

        proc = sub.Popen(args, stdout=sub.PIPE, stderr=sub.PIPE)
        out, err = proc.communicate()
        # print(f'process stdout: {out.decode()}')
        # print(f'process stderr: {err.decode()}')
        if proc.returncode == 0:
            print(f'successfully created {output_file}')
        else:
            print(f'error: could not create {output_file}')
            print(f'stderr: {err}')

    def _analyze_audio_levels(self, filepath, threshold):
        args = [
            'ffprobe',
            '-f',
            'lavfi',
            '-i',
            f'amovie={filepath},astats=metadata=1:reset=1',
            '-show_entries',
            'frame=pkt_pts_time:frame_tags=lavfi.astats.Overall.RMS_level',
            '-of',
            'csv=p=0'
        ]
        probe_process = sub.Popen(args, stdout=sub.PIPE, stderr=sub.PIPE)
        avg_volumes = {}
        print(f'analyzing audio of {filepath} ...')
        for timestamp, volume, *rest in get_time_and_levels(probe_process):
            # print(timestamp, volume, rest)
            avg = avg_volumes.setdefault(round(round(timestamp * 10) / 10, 1), [0, 0])
            avg[0] += volume  # sum
            avg[1] += 1  # count

        print(f'processing cuts ...')
        segments = []
        step = 0.1  # seconds
        begin, end = 0, None
        loud_count, silent_count = 0, 0
        loud_needed, silent_needed = 3, 5
        recording = False
        margin = 3
        for time, (acc, count) in avg_volumes.items():
            current = acc / count
            # print(f'{time}: {current}')
            if abs(current) != math.inf and int(current) > threshold:
                loud_count += 1
                silent_count = 0
            else:
                silent_count += 1
                loud_count = 0
            if not recording and loud_count == loud_needed:
                # print(f'RECORD START (-{loud_needed})')
                begin = time - step * (loud_needed + margin)
                recording = True
            elif recording and silent_count == silent_needed:
                # print(f'RECORD STOP (-{silent_needed})')
                end = time - step * (silent_needed - margin)
                recording = False
                segments.append((begin, end))
                # print(f'segment: {(begin, end)}')

        print(f'found {len(segments)} cuts')

        out, err = probe_process.communicate()
        # print(f'segments: {segments}')
        return segments


def main():
    if len(sys.argv) == 1:
        print('error: insufficient number of arguments', file=sys.stderr)
        sys.exit(1)
    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print('error: file does not exist', file=sys.stderr)

    slicer = AudioClipSlicer(input_path)
    slicer.run_montage(threshold=-42)
    # slicer._analyze_audio_levels(slicer.input_file, threshold=-42)
    


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print('error: caught exception')
        print(e)