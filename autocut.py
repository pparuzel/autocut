#!/usr/bin/env python3

import os
import math
import argparse
import subprocess as sub

from sys import stderr, exit
from datetime import timedelta
from tempfile import mkdtemp
from threading import Semaphore, Thread, Lock

MAJOR, MINOR, PATCH = 0, 1, 1
VERSION = f'{MAJOR}.{MINOR}.{PATCH}'

class EmptyConfig:
    """Helper placeholder class
    """
    def __getattribute__(self, name):
        return None


def get_levels_in_time(probe_process: sub.Popen):
    for line in probe_process.stdout:
        yield map(float, line.decode().strip().split(','))


class AutoCut:
    def __init__(self, input_file, output_base_name=None, config=None):
        """Constructs an AutoCut instance

        input_file       -- video/audio file to cut
        output_base_name -- base name of an output file
        config           -- namespace of an argument parser
        """
        self.check_utilities('ffmpeg', 'ffprobe')
        if not os.path.exists(input_file):
            print('error: file does not exist', file=stderr)
            exit(1)
        self.config = config if config else EmptyConfig()
        self.input_file = input_file
        input_base, extension = os.path.splitext(self.input_file)
        self.output_base = output_base_name if output_base_name else input_base
        self.extension = extension

    def run_montage(self, rms_threshold: float):
        """Executes the segmentation and audio analysis

        rms_threshold -- Maximum RootMeansSquare threshold level of noise
        """
        segments = self.audio_level_segmentation(rms_threshold)
        if not segments:
            print(f'warning: no cuts received', file=stderr)
            return
        temp_dir = mkdtemp(
            prefix=f'autocut_{self.output_base}_',
            dir=os.getcwd())
        print(f'created clips directory: {temp_dir}')
        logn = math.ceil(math.log(len(segments) - 1, 10))  # max width of index
        segments_path = os.path.join(temp_dir, 'segments.txt')
        count_guard, count = Lock(), 0

        def create_clip(segments_file, lock):
            nonlocal count
            file_base = f'{self.output_base}.{i+1:0{logn}}{self.extension}'
            output_file = os.path.join(temp_dir, file_base)
            success = True
            if not self.config.dry_run:
                success = self.slice_and_copy(start, end, output_file)
            lock.release()
            if success:
                with count_guard:
                    count += 1
                    print(
                        f'successful: {count} / {len(segments)}',
                        end='\r',
                        flush=True)
                segments_file.write(f'{file_base}: {start, end}\n')
            else:
                print(f'\nerror at {start, end}')
                segments_file.write(f'<no file>: {start, end}\n')

        with open(segments_path, 'w') as segments_file:
            jobs = []
            lock = Semaphore(8)
            for i, (start, end) in enumerate(segments):
                t = Thread(target=create_clip, args=(segments_file, lock))
                lock.acquire()
                jobs.append(t)
                t.start()
            for job in jobs:
                job.join()
        print()

        if self.config.dry_run and self.config.verbose:
            with open(segments_path, 'r') as segments_file:
                print('-' * 12)
                print(f'{segments_path}\n')
                print(segments_file.read())
        try:
            if self.config.dry_run:
                os.remove(segments_path)
            os.rmdir(temp_dir)
        except:
            pass

    def slice_and_copy(self, start: float, end: float, output_file):
        """Slices the input file at a section
        and copies to a separate file

        start       -- beginning of a section
        end         -- end of a section
        output_file -- file name to create a copy with
        """
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
        edit_process = sub.Popen(args, stdout=sub.PIPE, stderr=sub.PIPE)
        out, err = edit_process.communicate()
        # print(f'process stdout: {out.decode()}')
        # print(f'process stderr: {err.decode()}')
        return edit_process.returncode == 0

    def audio_level_segmentation(self, threshold: float):
        """Performs audio-level analysis and returns segments

        threshold -- Maximum RootMeansSquare threshold level of noise
        """
        volumes = {}  # for the purpose of averaging
        print(f'analyzing audio of {self.input_file} ...')
        probe_process = self._probe_rms(
            self.input_file,
            stdout=sub.PIPE,
            stderr=sub.PIPE)
        for timestamp, volume, *rest in get_levels_in_time(probe_process):
            average = volumes.setdefault(
                round(round(timestamp * 10) / 10, 1),
                [0, 0])
            average[0] += volume  # sum
            average[1] += 1  # count
        out, err = probe_process.communicate()
        print(f'processing cuts -- threshold: {threshold:.2f}...')
        segments = []
        time_step = 0.1  # seconds
        begin_time, end_time = None, None
        loud_count, silent_count = 0, 0
        # TODO: hardcoded values
        loud_needed, silent_needed = 3, 5  # 3 * 0.1 sec and 5 * 0.1 sec
        recording = False
        margin = 3
        for timestamp, (acc, count) in volumes.items():
            current = acc / count
            if self.config.trace_rms:
                print(f'trace: {timestamp}: {current}')
            if abs(current) != math.inf and int(current) > threshold:
                loud_count += 1
                silent_count = 0
            else:
                silent_count += 1
                loud_count = 0
            if not recording and loud_count == loud_needed:
                begin_time = timestamp - time_step * (loud_needed + margin)
                recording = True
            elif recording and silent_count == silent_needed:
                end_time = timestamp - time_step * (silent_needed - margin)
                recording = False
                segments.append((begin_time, end_time))

        if segments and segments[0] and segments[0][0] < 0:
            # TODO: this is ugly
            # If feasible, discard the possibility of a negative boundary
            del segments[0]
        print(f'found {len(segments)} cuts')
        return segments

    def scan_noise_level(self, duration=120, start=0):
        """Infers audio level for noise
        at a span of the video

        duration -- sample duration time in seconds
        start    -- starting point for the scan (in seconds)
        """
        acc, count = 0, 0
        max_vol, min_vol = -math.inf, math.inf
        probe_process = self._probe_rms(
            self.input_file,
            stdout=sub.PIPE,
            stderr=sub.PIPE)
        # calculate the stats
        for timestamp, volume, *rest in get_levels_in_time(probe_process):
            if int(timestamp) > start + duration:
                break
            if int(timestamp) < start:
                # TODO: O(n) to get to the start
                #       I think it could be O(1)
                continue
            max_vol = max(max_vol, volume)
            if volume != -math.inf:
                min_vol = min(min_vol, volume)
                acc += volume
                count += 1
        if count != 0:
            avg_vol = acc / count
        else:
            avg_vol = math.nan

        # find the most stable lower bound
        prev_vol, smallest_diff = math.inf, math.inf
        stable_volume = math.inf
        probe_process = self._probe_rms(
            self.input_file,
            stdout=sub.PIPE,
            stderr=sub.PIPE)
        for timestamp, volume, *rest in get_levels_in_time(probe_process):
            if int(timestamp) > duration:
                break
            if volume != -math.inf:
                if abs(volume - prev_vol) < smallest_diff and volume < avg_vol:
                    smallest_diff = abs(volume - prev_vol)
                    stable_volume = volume
                prev_vol = volume
        # calculate suggested noise
        suggest_noise = stable_volume - (stable_volume - avg_vol) * 0.3
        return suggest_noise, max_vol, min_vol, avg_vol

    def check_utilities(self, *utilities):
        """Checks whether utilities exist
        and return help message

        *utilities -- string parameters with names of utilities
        """
        must_exit = False
        for utility in utilities:
            try:
                sub.check_call(
                    [utility, '-h'],
                    stdout=sub.DEVNULL,
                    stderr=sub.DEVNULL)
            except FileNotFoundError:
                print(f'error: could not find {utility}', file=stderr)
                must_exit = True
        if must_exit:
            exit(1)

    def _probe_rms(self, filename, **kwargs):
        args = [
            'ffprobe',
            '-f',
            'lavfi',
            '-i',
            f'amovie={filename},astats=metadata=1:reset=1',
            '-show_entries',
            'frame=pkt_pts_time:frame_tags=lavfi.astats.Overall.RMS_level',
            '-of',
            'csv=p=0'
        ]
        return sub.Popen(args, **kwargs)


def run_autocut():
    parser = argparse.ArgumentParser(
        prog='autocut',
        description='video splitting based on noise threshold')

    parser.add_argument(
        'input_file',
        help='file to process')
    parser.add_argument(
        '-t', '--threshold',
        type=float,
        metavar='N',
        help='maximum RMS threshold level of noise')
    parser.add_argument(
        '-s', '--start-scan',
        type=float,
        default=0,
        metavar='<seconds>',
        help='time in seconds to start noise scan from (default=0)')
    parser.add_argument(
        '-d', '--scan-duration',
        type=float,
        default=120,
        metavar='<seconds>',
        help='duration time in seconds of the noise scan (default=120)')
    parser.add_argument(
        '--scan-noise',
        action='store_true',
        dest='scan_noise_only',
        help='scan noise only, skip the rest')
    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='do not execute')
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='provide debug information')
    parser.add_argument(
        '--trace-rms',
        action='store_true',
        help=argparse.SUPPRESS)
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s v{VERSION}')

    args = parser.parse_args()
    autocut = AutoCut(args.input_file, config=args)
    if not args.threshold:
        print('scanning noise level threshold ...')
        span = args.start_scan, args.start_scan + args.scan_duration
        print(f'sampling time span: {span}')
        args.threshold, max_vol, min_vol, avg_vol = autocut.scan_noise_level(
            duration=args.scan_duration,
            start=args.start_scan)
        print(f'''detected audio levels ({args.scan_duration} seconds)
            max: {max_vol}
            min: {min_vol}
            avg: {avg_vol}
            ---
            suggested noise level: {args.threshold}
            ''')
        if args.scan_noise_only:
            exit(0)
    autocut.run_montage(rms_threshold=args.threshold)
    exit(0)


if __name__ == '__main__':
    try:
        run_autocut()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print('error: caught unexpected exception', file=stderr)
        print(e, file=stderr)
        raise e
