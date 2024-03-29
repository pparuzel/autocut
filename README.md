# AutoCut
Video/audio voice splitter based on noise level

## Usage

1. Find a video/audio file.
```sh
$ ls
talking_video.mp4
```
1. Run `autocut` on the file and enjoy. You can also set the noise threshold
   manually with `-t`. This threshold represents the maximum value for noise
   which will separate it from the expected signal.
```
$ autocut.py talking_video.mp4
```
```
scanning noise level threshold ...
sampling time span: (0, 120)
detected audio levels (120 seconds)
            max: -37.322253
            min: -82.643269
            avg: -54.44065573627838
            ---
            suggested noise level: -56.34756092088351

analyzing audio of talking_video.mp4 ...
processing cuts ...
found 1798 cuts
created clips directory: /Users/test_user/examples/autocut_talking_video_4820osfp
successfully created talking_video.0001.mp4
successfully created talking_video.0002.mp4
...
successfully created talking_video.1798.mp4
```
1. Program outputs some information i.a. the number of clips.
```
$ ls
talking_video.mp4 autocut_talking_video_4820osfp
```
4. Program produces a unique directory with a name following the format:
   `autocut_<FILENAME>_<UNIQUEID>`.
```
$ ls -1 autocut_talking_video_4820osfp/
segments.txt
talking_video.0001.mp4
talking_video.0002.mp4
...
talking_video.1797.mp4
```
5. The directory contains all the clips as well as a `segments.txt` file
   (see below).
   * `segments.txt` - contains the list of all segments and their filenames
   * segments are of format: `<FILENAME>.<PART_ID>[.<EXTENSION>]: (<BEGIN>, <END>)`
   * `<BEGIN>` and `<END>` are represented in *seconds*

## Requirements

* FFmpeg utilities
  * ffmpeg
  * ffprobe
* Python 3.7+
