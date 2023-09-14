from pathlib import Path, PurePath
from pyprog import ProgressBar
from os import system as cmd
from os import chdir as cd
from os import makedirs
from os.path import exists, dirname
from time import sleep

FFmpeg = PurePath(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
CUETools = PurePath(r"S:\CUETools_2.2.2")
metaflac = PurePath(r"C:\ProgramData\chocolatey\bin\metaflac.exe")
in_dir = Path(input("Input Directory: "))
out_dir = Path(input("Output Directory: "))
in_flacs = tuple(in_dir.glob("**/*.flac"))
out_flacs = tuple([Path(str(out_dir)+"\\"+str(flac.relative_to(in_dir))) for flac in in_flacs])
assert len(in_flacs) == len(out_flacs)
flacs = tuple(zip(in_flacs, out_flacs))
progress = ProgressBar("Converting... ","",len(flacs))
cd(CUETools)
for count, flac in enumerate(flacs):
    progress.set_stat(count+1)
    progress.update()
    print("\noriginal: %s" % str(flac[0]))
    print("destination: %s\n" % str(flac[1]))
    if not exists(dirname(str(flac[1]))):
        makedirs(dirname(str(flac[1])))
    cmd("metaflac --export-picture-to=R:\cover \"%s\""  % str(flac[0]))
    cmd("CUETools.FLACCL.cmd.exe -o \"%s\" --lax -11 \"%s\"" % (str(flac[1]),str(flac[0])))
    cmd("metaflac --export-tags-to=- \"%s\" | metaflac --import-tags-from=- \"%s\"" % (str(flac[0]), str(flac[1])))
    if exists("R:\cover"):
        cmd("metaflac --import-picture-from=\"R:\cover\" \"%s\"" % str(flac[1]))
        cmd("del R:\cover")
progress.end()
