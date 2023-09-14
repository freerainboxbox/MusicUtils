# User is prompted for options:
# Usage: -i <input file/directory> -o <output file/directory> --mode <lossless/I/E/S/P> --resample-mode <original/sample rate/base> --base-multi --ffmpeg <path to ffmpeg.exe> --ffprobe <path to ffprobe.exe> --cue <path to CUETools> --metaflac <path to metaflac.exe> --resampler <path to ReSampler.exe> --cover-mode <embed/smart/separate> --replaygain
# -i and -o must be of the same type, either file or directory
# if --resample-mode is "original", do not resample
# if --resample-mode is a resample rate in Hz, resample to that rate
# however, if --base-multi is specified, resample to the smallest multiple of the sample rate given in resample-mode that is greater than or equal to the original sample rate
# if --resample-mode is "base", resample to either 44100 or 48000 Hz, whichever is an integer divisor of the original sample rate, and defaults to 44100 if neither is an integer divisor.
# however, if --base-multi is specified, resample to the smallest multiple of 44100 or 48000 Hz that is greater than or equal to the original sample rate.
# if cover-mode is "embed", embed cover art in the all output files (may use extra space due to all files in album having the same cover)
# if cover-mode is "smart", embed cover art if the file is a single track (determined through tags), otherwise, all files within a directory are part of the same album, remove all cover art and keep as a cover.jpg in the directory. This is the default mode.
# if cover-mode is "separate", remove all cover art and keep as a cover.jpg in the directory, throw an error if cover.jpg already exists and stop
# if --mode is "lossless", convert to FLAC using FLACCL
# if --mode is a letter option, take source file, put it through ffmpeg -i <input> -c:a pcm_s24le -f wav pipe:1 | CUETools.LossyWAV.exe - -<mode> --stdout | CUETools.FLACCL.cmd.exe -o <output> --lax -11 -
# if --replaygain is specified, remove all existing replaygain tags, then add replaygain tags album (or single) by album (or single), using metaflac --add-replay-gain.
# if --replaygain is not specified, do not remove existing replaygain tags, instead copy them over.

from pathlib import Path, PurePath
import shutil
import progressbar
from subprocess import check_output, DEVNULL
def cmd(command):
    return check_output(command, shell=True, text=True, stderr=DEVNULL)
from os import chdir as cd
from os import getenv
from os import mkdir as mkdir
from os.path import exists, dirname
def printerr(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
import argparse
from math import ceil


# Parse command line arguments.
parser = argparse.ArgumentParser(description="Converts FLAC files to lossless or lossy FLAC files.")
parser.add_argument("-i", "--input", help="Input file or directory.", required=True)
parser.add_argument("-o", "--output", help="Output file or directory.", required=True)
parser.add_argument("--mode", help="Mode to use. One of lossless, I, E, S, P.", required=True)
parser.add_argument("--resample-mode", help="Resample mode. One of original, sample rate (a number), base.", required=True)
parser.add_argument("--base-multi", help="If resample-mode is base, resample to the smallest multiple of 44100 or 48000 that is greater than or equal to the original sample rate."
                    " If resample-mode is a sample rate, resample to the smallest multiple of the given sample rate that is greater than or equal to the original sample rate.", action="store_true")
parser.add_argument("--ffmpeg", help="Path to ffmpeg binary.", required=True)
parser.add_argument("--ffprobe", help="Path to ffprobe binary.", required=True)
parser.add_argument("--cue", help="Path to CUETools binary directory.", required=True)
parser.add_argument("--metaflac", help="Path to metaflac binary.", required=True)
parser.add_argument("--resampler", help="Path to ReSampler binary.", required=True)
parser.add_argument("--cover-mode", help="Cover mode. One of embed, smart, separate.", required=False, default="smart")
parser.add_argument("--replaygain", help="Recalculate replaygain tags.", action="store_true")
args = parser.parse_args()

# Set up paths.
input_path = Path(args.input)
output_path = Path(args.output)
ffmpeg_path = Path(args.ffmpeg)
ffprobe_path = Path(args.ffprobe)
cue_path = Path(args.cue)
metaflac_path = Path(args.metaflac)
resampler_path = Path(args.resampler)
temp_path = Path(getenv('temp')) / ".music_library_normalizer_tmp"
temp_path.mkdir(exist_ok=True)

mode = args.mode
resample_mode = args.resample_mode

base_multi = args.base_multi
baserates = (44100, 48000)

replaygain = args.replaygain

cover_mode = args.cover_mode

# Ensure that input and output paths are of the same type.
if input_path.is_file() != output_path.is_file():
    print("Input and output paths must be of the same type.")
    exit(1)

# Ensure that input and output paths are not the same.
if input_path == output_path:
    print("Input and output paths must not be the same.")
    exit(1)

# Ensure that input and output paths are not subpaths of each other.
if input_path in output_path.parents or output_path in input_path.parents:
    print("Input and output paths must not be subpaths of each other.")
    exit(1)

# Find how many FLAC files are in the directory tree of the input path.
flac_count = 0
for path in input_path.rglob("*"):
    if path.suffix == ".flac":
        flac_count += 1
# Make a progressbar2.Bar() with flac_count steps. Give a percentage and ETA.
print("Total files: " + str(flac_count))
processed_count = 0
progress_bar = progressbar.ProgressBar(max_value=flac_count, widgets=[progressbar.Bar(), progressbar.Percentage(), progressbar.ETA()])


# Normalizes the file, performs metadata operations, except for album cover and replaygain (since these are album-dependent).
def normalizeFile(infile: Path, outfile: Path, temp_path: Path, resample_mode: str, base_multi: bool, ffmpeg_path: Path, metaflac_path: Path, cue_path: Path):
    # Check if input file is a FLAC file. Store as a boolean.
    is_flac = infile.suffix == ".flac"
    
    #
    # Get target sample rate for this file.
    #
    sample_rate = 0
    original_rate = int(cmd(f"{ffprobe_path} -v error -select_streams a:0 -show_entries stream=sample_rate -of default=noprint_wrappers=1:nokey=1 \"{infile}\""))
    if resample_mode == "original":
        # Get original sample rate using ffprobe_path.
        sample_rate = original_rate
    elif resample_mode == "base":
        if base_multi:
            multis = [ceil(sample_rate / baserate)*baserate for baserate in baserates]
            sample_rate = min(multis)
        else:
            sample_rate = baserates[0]
            # Loop backwards through baserates
            for baserate in baserates[::-1]:
                if original_rate % baserate == 0:
                    sample_rate = baserate
                    break
    else:
        if base_multi:
            sample_rate = ceil(original_rate / int(resample_mode))*int(resample_mode)
        else:
            sample_rate = int(resample_mode)

    #
    # Get the bit depth of input file.
    #
    bit_depth = int(cmd(f"{ffprobe_path} -v error -select_streams a:0 -show_entries stream=bits_per_raw_sample -of default=noprint_wrappers=1:nokey=1 \"{infile}\""))
    
    #
    #
    # Normalize the file.
    #
    #

    #
    # Resample step
    #
    re_outfile = "" # Either the original FLAC, or temp2.wav.
    if resample_mode != "original":
        # BUG: Filename errors for special characters. Rename infile to current.flac and restore to original name after resampling.
        # If input file is FLAC, re_infile is infile.
        if is_flac:
            re_infile = infile
        # If input file is not FLAC, convert infile to temp1.wav (as re_infile) with the same sample rate as original file.
        else:
            re_infile = temp_path / "temp1.wav"
            cmd(f"{ffmpeg_path} -i \"{infile}\" -ar {original_rate} \"{re_infile}\"")
        re_outfile = temp_path / "temp2.wav"
        cmd(f"\"{resampler_path}\" -i \"{re_infile}\" -o \"{re_outfile}\" -r {sample_rate} --mt --doubleprecision -b {bit_depth}")
        # If temp1.wav exists, delete it.
        if temp_path in re_infile.parents:
            cmd(f"del \"{re_infile}\"")
    # Original, so no resampling.
    else:
        # If input file is FLAC, re_outfile is infile (no conversion).
        if is_flac:
            re_outfile = infile
        # If input file is not FLAC, convert infile to temp1.wav) with the same sample rate as original file.
        else:
            re_outfile = temp_path / "temp2.wav"
            cmd(f"{ffmpeg_path} -i \"{infile}\" -ar {original_rate} \"{re_outfile}\"")
    
    #
    # Quantization and compression step
    #
    # Create outfile's directory recursively, if it doesn't exist
    if not outfile.parent.is_dir():
        outfile.parent.mkdir(parents=True) # FIXME: Output directory is not being created.
    if mode == "lossless":
        cmd(f"\"{cue_path}\CUETools.FLACCL.cmd.exe\" -o \"{outfile}\" --lax -11 \"{re_outfile}\"")
    # Use quantization
    else:
        if re_outfile.suffix == ".flac":
            # Convert re_outfile to temp3.wav.
            temp3 = temp_path / "temp3.wav"
            if bit_depth == 16:
                cmd(f"{ffmpeg_path} -i \"{re_outfile}\" -c:a pcm_s16le -f wav \"{temp3}\"")
            else:
                # Default to 24 bits in the worst case. Theoretically doesn't matter because of the wasted_bits field.
                cmd(f"{ffmpeg_path} -i \"{re_outfile}\" -c:a pcm_s24le -f wav \"{temp3}\"")
        else:
            # Move temp2.wav to temp3.wav.
            temp3 = temp_path / "temp3.wav"
            cmd(f"move \"{re_outfile}\" \"{temp3}\"")
        cmd(f"\"{cue_path}\CUETools.LossyWAV.exe\"  \"{temp3}\" --stdout -{mode} | \"{cue_path}\CUETools.FLACCL.cmd.exe\" -o \"{outfile}\" --lax -11 -")

    # Clear all files in the temp directory.
    for file in temp_path.iterdir():
        cmd(f"del \"{file}\"")
    # Copy tags from infile to outfile.
    cmd("metaflac --export-tags-to=- \"%s\" | metaflac --import-tags-from=- \"%s\"" % (infile, outfile))
    if replaygain:
        # Get rid of replaygain information in outfile.
        cmd(f"{metaflac_path} --remove-replay-gain \"{outfile}\"")
    # Increment progress bar.
    global processed_count
    processed_count += 1
    progress_bar.update(processed_count)

def DirIsAnAlbum(query):
    # Returns 1 if the directory is an album,
    # 0 if it is not (an artist directory with singles and albums)
    # Negative values are exceptional cases:
    # -1 if contains only one FLAC file (an artist directory with only one single so far)
    # -2 if it contains no FLAC files (i.e., a base directory for a multidisc album).
    # A directory is an album if it has multiple FLAC files, and all FLAC files share the same album name (same album tag).

    # Check if this directory only has one file ending in ".flac".
    flac_files = [file for file in query.iterdir() if file.suffix == ".flac"]
    if len(flac_files) == 1:
        return -1
    elif len(flac_files) == 0:
        return -2
    else:
        # Get the album name of the first FLAC file using metaflac.
        album_name = cmd(f"{metaflac_path} --show-tag=ALBUM \"{flac_files[0]}\"").split("=")[1].strip()
        # Check if all FLAC files have the same album name.
        for file in flac_files:
            if cmd(f"{metaflac_path} --show-tag=ALBUM \"{file}\"").split("=")[1].strip() != album_name:
                return 0
        return 1

def normalizeDirectory(input_path, output_path, mode, resample_mode, base_multi, cue_path, metaflac_path, ffmpeg_path, ffprobe_path, resampler_path, temp_path):
    # Normalize a directory of FLAC files. normalizeDirectory is recursive, acting on the files first, then the subdirectories.
    # If the directory is an album, normalize all FLAC files in the directory.
    # If the directory is an artist directory, normalize all FLAC files in the directory and subdirectories.
    # If the directory is a multidisc album, normalize all FLAC files in the directory and subdirectories.
    cd(input_path)
    # Check if this directory is an album.
    match DirIsAnAlbum(input_path):
        # If this directory is an album, normalize all FLAC files in the directory.
        case 1:
            for file in input_path.iterdir():
                if file.suffix == ".flac":
                    normalizeFile(file, output_path / file.name, temp_path, resample_mode, base_multi, ffmpeg_path, metaflac_path, cue_path)
            # TODO: Finish the normalization of the directory itself (i.e. moving files, calculating replaygain, etc.)
            # Copy all non-flac files to the output directory.
            for file in input_path.iterdir():
                if file.suffix != ".flac" and file.is_file():
                    shutil.copy(file, output_path)
            if replaygain:
                cmd(f"{metaflac_path} --add-replay-gain \"{output_path}\\*.flac\"")
            # else: replaygain was already copied over.
            # In this case, "smart" and "separate" are the same, and already done.
            # If "embed" is specified, then additional steps are needed.
            if cover_mode == "embed":
                # TODO: Check if there is a cover art file in the directory. Extract if it doesn't exist. If no embedded cover art is found in any file, warn and skip.
                # Embed the cover art (first .jpg) in all FLAC files.
                cover = [file for file in input_path.iterdir() if file.suffix == ".jpg"][0]
                for file in output_path.iterdir():
                    # Embed the cover art in this file.
                    cmd(f"{metaflac_path} --import-picture-from=\"{cover}\" \"{file}\"")
        # If this directory is an artist directory, normalize all FLAC files in the directory and subdirectories.
        case 0:
            filesExist = False
            # In this directory only, normalize all FLAC files.
            for file in input_path.iterdir():
                filesExist = True
                if file.suffix == ".flac":
                    normalizeFile(file, output_path / file.name, temp_path, resample_mode, base_multi, ffmpeg_path, metaflac_path, cue_path)
                    if replaygain:
                        # Calculate replaygain for this file only.
                        cmd(f"{metaflac_path} --add-replay-gain {file}")
                    if cover_mode == "embed" or cover_mode == "smart":
                        # Get the embedded cover art for this file, put it in the temp directory.
                        cmd(f"{metaflac_path} --export-picture-to=\"{temp_path}\\cover.jpg\" \"{file}\"")
                        # Embed the cover art in the output file.
                        cmd(f"{metaflac_path} --import-picture-from=\"{temp_path}\\cover.jpg\" \"{output_path}\\{file.name}\"")
                        # Delete the temp cover art file.
                        cmd(f"del \"{temp_path}\\cover.jpg\"")
            # Recursively normalize all subdirectories.
            for dir in input_path.iterdir():
                if dir.is_dir():
                    # Get the new output path for this subdirectory.
                    new_output_path = output_path / dir.name
                    # Create the new output directory.
                    mkdir(new_output_path)
                    # Normalize the subdirectory.
                    normalizeDirectory(dir, new_output_path, mode, resample_mode, base_multi, cue_path, metaflac_path, ffmpeg_path, ffprobe_path, resampler_path, temp_path)
                    cd(input_path)
            if filesExist and cover_mode == "separate":
                printerr(f"WARNING: cover_mode=separate specified and {input_path} has singles. Not copying cover art.")
            
        # Only one single in this directory.
        case -1:
            # Normalize the single.
            flac_file = [file for file in input_path.iterdir() if file.suffix == ".flac"][0]
            normalizeFile(flac_file, output_path, mode, resample_mode, base_multi, cue_path, metaflac_path, ffmpeg_path, ffprobe_path, resampler_path, temp_path)
            if replaygain:
                # Calculate replaygain for this file only.
                cmd(f"{metaflac_path} --add-replay-gain {flac_file}")
            # Copy all non-flac files to the output directory.
            for file in input_path.iterdir():
                if file.suffix != ".flac" and file.is_file():
                    shutil.copy(file, output_path)
            if cover_mode == "embed" or cover_mode == "smart":
                # Get the embedded cover art for this file, put it in the temp directory.
                cmd(f"{metaflac_path} --export-picture-to=\"{temp_path}\\cover.jpg\" \"{flac_file}\"")
                # Embed the cover art in the output file.
                cmd(f"{metaflac_path} --import-picture-from=\"{temp_path}\\cover.jpg\" \"{output_path}\\{flac_file.name}\"")
                # Delete the temp cover art file.
                cmd(f"del \"{temp_path}\\cover.jpg\"")
            else: # cover_mode == "separate"
                # Export the cover art to the output directory.
                cmd(f"{metaflac_path} --export-picture-to=\"{output_path}\\cover.jpg\" \"{flac_file}\"")
        # No FLAC files in this directory.
        case -2:
            # Copy all files to the output directory, recursively.
            for file in input_path.iterdir():
                if file.is_file():
                    shutil.copy(file, output_path)
            # Normalize all the discs.
            for dir in input_path.iterdir():
                if dir.is_dir():
                    # Get the new output path for this subdirectory.
                    new_output_path = output_path / dir.name
                    # Create the new output directory.
                    new_output_path.mkdir(parents=True, exist_ok=True)
                    # Normalize the subdirectory.
                    normalizeDirectory(dir, new_output_path, mode, resample_mode, base_multi, cue_path, metaflac_path, ffmpeg_path, ffprobe_path, resampler_path, temp_path)
                    cd(input_path)

if __name__ == "__main__":
    normalizeDirectory(input_path, output_path, mode, resample_mode, base_multi, cue_path, metaflac_path, ffmpeg_path, ffprobe_path, resampler_path, temp_path)