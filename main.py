#!/usr/bin/env python3.7

import sys
import os
import math
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

    def run(self):
        sections = self._analyze_audio_levels(self.input_file, threshold=22)
        if not sections:
            print(f'warning: no cuts received')
            return
        if math.log(len(sections), 10) > 3:
            print(f'error: too many sections')
            sys.exit(1)
        for i, (start, end) in enumerate(sections):
            self._slice_and_copy(start, end, output_file=f'{self.output_base_name}.{i+1:03}{self.extension}')
            break  # REMOVE THIS

    def _slice_and_copy(self, start, end, output_file):
        args = [
            'ffmpeg',
            '-ss',
            str(timedelta(seconds=start)),
            '-i',
            self.input_file,
            '-c',
            'copy',
            '-to',
            str(timedelta(seconds=end)),
            output_file
        ]
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
            # 'frame=pkt_pts_time:frame_tags=lavfi.astats.Overall.RMS_level,lavfi.astats.1.RMS_level,lavfi.astats.2.RMS_level',
            'frame=pkt_pts_time:frame_tags=lavfi.astats.Overall.RMS_difference',
            '-of',
            'csv=p=0'
        ]
        probe_process = sub.Popen(args, stdout=sub.PIPE, stderr=sub.PIPE)
        avg_volumes = {}
        # acc = 0
        # prev_t = 0
        print(f'analyzing audio of {filepath} ...')
        for timestamp, volume, *rest in get_time_and_levels(probe_process):
            avg = avg_volumes.setdefault(round(round(timestamp * 3) / 3, 1), [0, 0])
            avg[0] += volume * 1000  # sum
            avg[1] += 1  # count
            # if acc > 1:
            #     print(timedelta(seconds=timestamp), volume * 1000, rest)
            #     acc = 0
            # acc += timestamp - prev_t
            # prev_t = timestamp

        print(f'processing cuts ...')
        sections = []
        begin, end = None, None
        acc_0, count_0 = avg_volumes[0.0]
        prev = acc_0 / count_0
        for time, (acc, count) in avg_volumes.items():
            current = acc / count
            print(f'{time}: {current}')
            if current - prev > threshold:
                if begin and end:
                    # print(f'CUT FROM {begin} TO {end}')
                    sections.append((begin, end))
                    begin, end = None, None
                begin = time
            elif current - prev < -threshold:
                end = time
            prev = current
        if begin and end:
            # print(f'LAST CUT FROM {begin} TO {end}')
            sections.append((begin, end))
            begin, end = None, None
        print(f'found {len(sections)} cuts')

        out, err = probe_process.communicate()
        return []#sections


def main():
    if len(sys.argv) == 1:
        print('error: insufficient number of arguments', file=sys.stderr)
        sys.exit(1)
    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print('error: file does not exist', file=sys.stderr)

    slicer = AudioClipSlicer(input_path)
    slicer.run()
    


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print('error: caught exception')
        print(e)