from pathlib import Path, PurePath
from pyprog import ProgressBar
from os import system as cmd
from os import chdir as cd
from os import makedirs
from os.path import exists, dirname
from time import sleep

in_dir = Path(input("Input Directory: "))
out_dir = Path(input("Output Directory: "))
in_covers = tuple(in_dir.glob("**/*.jpg"))+tuple(in_dir.glob("**/*.png"))
out_covers = tuple([Path(str(out_dir)+"\\"+str(cover.relative_to(in_dir))) for cover in in_covers])
assert len(in_covers) == len(out_covers)
covers = tuple(zip(in_covers, out_covers))
progress = ProgressBar("Transferring... ","",len(covers))
for count, cover in enumerate(covers):
    progress.set_stat(count+1)
    progress.update()
    print("\noriginal: %s" % str(cover[0]))
    print("destination: %s\n" % str(cover[1]))
    if not exists(dirname(str(cover[1]))):
        makedirs(dirname(str(cover[1])))
    cmd("copy \"%s\" \"%s\"" % (str(cover[0]), str(cover[1])))
progress.end()