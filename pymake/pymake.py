#! /usr/bin/env python
"""
Make a binary executable for a FORTRAN program, such as MODFLOW.
"""
from __future__ import print_function

__author__ = "Christian D. Langevin"
__date__ = "October 26, 2014"
__version__ = "1.1.0"
__maintainer__ = "Christian D. Langevin"
__email__ = "langevin@usgs.gov"
__status__ = "Production"
__description__ = '''
This is the pymake program for compiling fortran source files, such as
the source files that come with MODFLOW. The program works by building
a directed acyclic graph of the module dependencies and then compiling
the source files in the proper order.
'''

import os
import sys
import shutil
import subprocess
import argparse
from .dag import order_source_files, order_c_source_files
import datetime

try:
    from flopy import is_exe as flopy_is_exe
    flopy_avail = True
except:
    flopy_avail = False

def parser():
    '''
    Construct the parser and return argument values
    '''
    description = __description__
    parser = argparse.ArgumentParser(description=description,
                                     epilog='''Note that the source directory
                                     should not contain any bad or duplicate
                                     source files as all source files in the
                                     source directory will be built and
                                     linked.''')
    parser.add_argument('srcdir', help='Location of source directory')
    parser.add_argument('target', help='Name of target to create')
    parser.add_argument('-fc', help='Fortran compiler to use (default is gfortran)',
                        default='gfortran', choices=['ifort', 'gfortran'])
    parser.add_argument('-cc', help='C compiler to use (default is gcc)',
                        default='gcc', choices=['gcc', 'clang'])
    parser.add_argument('-ar', '--arch',
                        help='Architecture to use for ifort (default is intel64)',
                        default='intel64', choices=['ia32', 'ia32_intel64', 'intel64'])
    parser.add_argument('-mc', '--makeclean', help='Clean files when done',
                        action='store_true')
    parser.add_argument('-dbl', '--double', help='Force double precision',
                        action='store_true')
    parser.add_argument('-dbg', '--debug', help='Create debug version',
                        action='store_true')
    parser.add_argument('-e', '--expedite',
                        help='''Only compile out of date source files.
                        Clean must not have been used on previous build.
                        Does not work yet for ifort.''',
                        action='store_true')
    parser.add_argument('-dr', '--dryrun',
                        help='''Do not actually compile.  Files will be
                        deleted, if --makeclean is used.
                        Does not work yet for ifort.''',
                        action='store_true')
    parser.add_argument('-sd', '--subdirs',
                        help='''Include source files in srcdir
                        subdirectories.''',
                        action='store_true')
    parser.add_argument('-ff', '--fflags',
                        help='''Additional fortran compiler flags.''',
                        default=None)
    parser.add_argument('-mf', '--makefile',
                        help='''Create a standard makefile.''',
                        action='store_true')
    parser.add_argument('-cs', '--commonsrc',
                        help='''Additional directory with common source files.''',
                        default=None)
    args = parser.parse_args()
    return args


def initialize(srcdir, target, commonsrc):
    '''
    Remove temp source directory and target, and then copy source into
    source temp directory.  Return temp directory path.
    '''
    # remove the target if it already exists
    srcdir_temp = os.path.join('.', 'src_temp')
    objdir_temp = os.path.join('.', 'obj_temp')
    moddir_temp = os.path.join('.', 'mod_temp')

    # remove srcdir_temp and copy in srcdir
    try:
        os.remove(target)
    except:
        pass
    try:
        shutil.rmtree(srcdir_temp)
    except:
        pass
    shutil.copytree(srcdir, srcdir_temp)

    # copy files from a specified common source directory if
    # commonsrc is not None
    if commonsrc is not None:
        pth = os.path.basename(os.path.normpath(commonsrc))
        pth = os.path.join(srcdir_temp, pth)
        shutil.copytree(commonsrc, pth)

    # set srcdir_temp
    srcdir_temp = os.path.join(srcdir_temp)

    # if they don't exist, create directories for objects and mods
    if not os.path.exists(objdir_temp):
        os.makedirs(objdir_temp)
    if not os.path.exists(moddir_temp):
        os.makedirs(moddir_temp)

    return srcdir_temp, objdir_temp, moddir_temp


def clean(srcdir_temp, objdir_temp, moddir_temp, objext, winifort):
    """
    Remove mod and object files, and remove the temp source directory.

    """
    # clean things up
    print('\nCleaning up temporary source, object, and module files...')
    filelist = os.listdir('.')
    delext = ['.mod', objext]
    for f in filelist:
        for ext in delext:
            if f.endswith(ext):
                os.remove(f)
    shutil.rmtree(srcdir_temp)
    shutil.rmtree(objdir_temp)
    shutil.rmtree(moddir_temp)
    if winifort:
        os.remove('compile.bat')
    return


def get_ordered_srcfiles(srcdir_temp, include_subdir=False):
    '''
    Create a list of ordered source files (both fortran and c).  Ordering
    is build using a directed acyclic graph to determine module dependencies.
    '''
    # create a list of all c(pp), f and f90 source files

    templist = []
    for path, subdirs, files in os.walk(srcdir_temp):
        for name in files:
            if not include_subdir:
                if path != srcdir_temp:
                    continue
            f = os.path.join(os.path.join(path, name))
            templist.append(f)
    cfiles = []  # mja
    srcfiles = []
    for f in templist:
        if f.lower().endswith('.f') or f.lower().endswith('.f90') \
                or f.lower().endswith('.for') or f.lower().endswith('.fpp'):
            srcfiles.append(f)
        elif f.lower().endswith('.c') or f.lower().endswith('.cpp'):  # mja
            cfiles.append(f)  # mja

    # orderedsourcefiles = order_source_files(srcfiles) + \
    #                     order_c_source_files(cfiles)


    srcfileswithpath = []
    for srcfile in srcfiles:
        s = os.path.join(srcdir_temp, srcfile)
        s = srcfile
        srcfileswithpath.append(s)

    # from mja
    cfileswithpath = []
    for srcfile in cfiles:
        s = os.path.join(srcdir_temp, srcfile)
        s = srcfile
        cfileswithpath.append(s)

    # order the source files using the directed acyclic graph in dag.py
    orderedsourcefiles = []
    if len(srcfileswithpath) > 0:
        orderedsourcefiles += order_source_files(srcfileswithpath)
        
    if len(cfileswithpath) > 0:
        orderedsourcefiles += order_c_source_files(cfileswithpath)

    return orderedsourcefiles


def create_openspec(srcdir_temp):
    '''
    Create a new openspec.inc file that uses STREAM ACCESS.  This is specific
    to MODFLOW.
    '''
    files = ['openspec.inc', 'FILESPEC.INC']
    dirs = [d[0] for d in os.walk(srcdir_temp)]
    for d in dirs:
        for f in files:
            fname = os.path.join(d, f)
            if os.path.isfile(fname):
                print('replacing..."{}"'.format(fname))
                f = open(fname, 'w')
                line = "c -- created by pymake.py\n" + \
                       "      CHARACTER*20 ACCESS,FORM,ACTION(2)\n" + \
                       "      DATA ACCESS/'STREAM'/\n" + \
                       "      DATA FORM/'UNFORMATTED'/\n" + \
                       "      DATA (ACTION(I),I=1,2)/'READ','READWRITE'/\n" + \
                       "c -- end of include file\n"
                f.write(line)
                f.close()
    return


def out_of_date(srcfile, objfile):
    ood = True
    if os.path.exists(objfile):
        t1 = os.path.getmtime(objfile)
        t2 = os.path.getmtime(srcfile)
        if t1 > t2:
            ood = False
    return ood


# determine if iso_c_binding is used so that correct
# gcc and clang compiler flags can be set
def get_iso_c(srcfiles):
    use_iso_c = False
    for srcfile in srcfiles:
        try:
            f = open(srcfile, 'rb')
        except:
            print('get_f_nodelist: could not open {0}'.format(os.path.basename(srcfile)))
            continue
        lines = f.read()
        lines = lines.decode('ascii', 'replace').splitlines()
        # develop a list of modules in the file
        for idx, line in enumerate(lines):
            linelist = line.strip().split()
            if len(linelist) == 0:
                continue
            if linelist[0].upper() == 'USE':
                modulename = linelist[1].split(',')[0].upper()
                if 'ISO_C_BINDING' == modulename:
                    return True
    return False

def flag_available(flag):
    """
    Determine if a specified flag exists
    """
    found = False
    # determin the gfortran command line flags available
    logfn = 'gfortran.txt'
    errfn = 'gfortran.err'
    logfile = open(logfn, 'w')
    errfile = open(errfn, 'w')
    proc = subprocess.Popen(["gfortran", "--help", "-v"],
                            stdout=logfile, stderr=errfile)
    ret_code = proc.wait()
    logfile.close()
    errfile.close()
    # read data
    f = open(logfn, 'r')
    lines = f.readlines()
    for line in lines:
        if flag.lower() in line.lower():
            found=True
            break
    f.close()
    # remove file
    os.remove(logfn)
    os.remove(errfn)
    # return
    return found


def compile_with_gnu(srcfiles, target, cc, objdir_temp, moddir_temp,
                     expedite, dryrun, double, debug, fflags,
                     srcdir, srcdir2, makefile):
    """
    Compile the program using the gnu compilers (gfortran and gcc)

    """

    # For horrible windows issue
    shellflg = False
    if sys.platform == 'win32':
        shellflg = True

    # fortran compiler switches
    fc = 'gfortran'
    if debug:
        # Debug flags
        compileflags = ['-g',
                        '-fcheck=all',
                        '-fbacktrace',
                        '-fbounds-check'
                        ]
    else:
        # Production version
        compileflags = ['-O2', '-fbacktrace',]
        if not sys.platform == 'win32':
            lflag = flag_available('-ffpe-summary')
            if lflag:
                compileflags.append('-ffpe-summary=overflow')
    objext = '.o'
    if double:
        compileflags.append('-fdefault-real-8')
        compileflags.append('-fdefault-double-8')
    if fflags is not None:
        t = fflags.split()
        for fflag in t:
            compileflags.append('-'+fflag)


    # C/C++ compiler switches -- thanks to mja
    if debug:
        cflags = ['-O0', '-g']
    else:
        cflags = ['-O3']

    # syslibs
    syslibs = []
    if sys.platform != 'win32':
        syslibs.append('-lc')

    # Add -D-UF flag for C code if ISO_C_BINDING is not used in Fortran
    # code that is linked to C/C++ code
    # -D_UF defines UNIX naming conventions for mixed language compilation.
    use_iso_c = get_iso_c(srcfiles)
    if not use_iso_c:
        cflags.append('-D_UF')

    # build object files
    print('\nCompiling object files...')
    objfiles = []
    for srcfile in srcfiles:
        cmdlist = []
        iscfile = False
        if srcfile.endswith('.c') or srcfile.endswith('.cpp'):  # mja
            iscfile = True
            cmdlist.append(cc)  # mja
            for switch in cflags:  # mja
                cmdlist.append(switch)  # mja
        else:  # mja
            cmdlist.append(fc)
            for switch in compileflags:
                cmdlist.append(switch)
        cmdlist.append('-c')
        cmdlist.append(srcfile)

        # object file name and location
        srcname, srcext = os.path.splitext(srcfile)
        srcname = srcname.split(os.path.sep)[-1]
        objfile = os.path.join(objdir_temp, srcname + '.o')
        cmdlist.append('-o')
        cmdlist.append(objfile)

        if not iscfile:
            # put object files in objdir_temp
            cmdlist.append('-I' + objdir_temp)
            # put module files in moddir_temp
            cmdlist.append('-J' + moddir_temp)

        # If expedited, then check if object file is out of date (if exists).
        # No need to compile if object file is newer.
        compilefile = True
        if expedite:
            if not out_of_date(srcfile, objfile):
                compilefile = False

        # Compile
        if compilefile:
            s = ''
            for c in cmdlist:
                s += c + ' '
            print(s)
            if not dryrun:
                #subprocess.check_call(cmdlist, shell=shellflg)
                proc = subprocess.Popen(cmdlist, shell=shellflg,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                stdout_data, stderr_data = proc.communicate()
                if proc.returncode != 0:
                    msg = '{} failed, '.format(cmdlist) + \
                          'status code {} '.format(proc.returncode) + \
                          'stdout {} '.format(stdout_data) + \
                          'stderr {}'.format(stderr_data)
                    print(msg)
                    return proc.returncode

        # Save the name of the object file so that they can all be linked
        # at the end
        objfiles.append(objfile)

    # Build the link command and then link
    msg = '\nLinking object files ' + \
          'to make {}...'.format(os.path.basename(target))
    print(msg)
    cmd = fc + ' '
    cmdlist = []
    cmdlist.append(fc)
    for switch in compileflags:
        cmd += switch + ' '
        cmdlist.append(switch)
    cmdlist.append('-o')
    cmdlist.append(os.path.join('.', target))
    for objfile in objfiles:
        cmdlist.append(objfile)
    for switch in syslibs:
        cmdlist.append(switch)
    s = ''
    for c in cmdlist:
        s += c + ' '
    print(s)
    if not dryrun:
        #subprocess.check_call(cmdlist, shell=shellflg)
        proc = subprocess.Popen(cmdlist, shell=shellflg,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        stdout_data, stderr_data = proc.communicate()
        if proc.returncode != 0:
            msg = '{} failed, '.format(cmdlist) + \
                  'status code {} '.format(proc.returncode) + \
                  'stdout {} '.format(stdout_data) + \
                  'stderr {}'.format(stderr_data)
            print(msg)
            return proc.returncode

    # create makefile
    if makefile:
        create_makefile(target, srcdir, srcdir2, objfiles,
                        fc, compileflags, cc, cflags, syslibs,
                        modules=['-I', '-J'])

    # return
    return 0


def compile_with_mac_ifort(srcfiles, target, cc,
                           objdir_temp, moddir_temp,
                           expedite, dryrun, double, debug, fflags,
                           srcdir, srcdir2, makefile):
    """
    Make target on Mac OSX
    """
    # fortran compiler switches
    fc = 'ifort'
    if debug:
        compileflags = [
            '-O0',
            '-debug',
            'all',
            '-no-heap-arrays',
            '-fpe0',
            '-traceback'
        ]
    else:
        # production version compile flags
        compileflags = [
            '-O2',
            '-no-heap-arrays',
            '-fpe0',
            '-traceback'
        ]
    if double:
        compileflags.append('-r8')
        compileflags.append('-double_size')
        compileflags.append('64')
    if fflags is not None:
        t = fflags.split()
        for fflag in t:
            compileflags.append('-'+fflag)

    # C/C++ compiler switches
    if debug:
        cflags = ['-O0', '-g']
    else:
        cflags = ['-O3']
    syslibs = ['-lc']
    # Add -D-UF flag for C code if ISO_C_BINDING is not used in Fortran
    # code that is linked to C/C++ code
    # -D_UF defines UNIX naming conventions for mixed language compilation.
    use_iso_c = get_iso_c(srcfiles)
    if not use_iso_c:
        cflags.append('-D_UF')

    # build object files
    print('\nCompiling object files...')
    objfiles = []
    for srcfile in srcfiles:
        cmdlist = []
        if srcfile.endswith('.c') or srcfile.endswith('.cpp'):  # mja
            cmdlist.append(cc)  # mja
            for switch in cflags:  # mja
                cmdlist.append(switch)  # mja
        else:  # mja
            cmdlist.append(fc)

            # put module files in moddir_temp
            cmdlist.append('-module')
            cmdlist.append('./' + moddir_temp + '/')

            for switch in compileflags:
                cmdlist.append(switch)

        cmdlist.append('-c')
        cmdlist.append(srcfile)

        # object file name and location
        srcname, srcext = os.path.splitext(srcfile)
        srcname = srcname.split(os.path.sep)[-1]
        objfile = os.path.join('.', objdir_temp, srcname + '.o')
        cmdlist.append('-o')
        cmdlist.append(objfile)

        # If expedited, then check if object file is out of date (if exists).
        # No need to compile if object file is newer.
        compilefile = True
        if expedite:
            if not out_of_date(srcfile, objfile):
                compilefile = False

        # Compile
        if compilefile:
            s = ''
            for c in cmdlist:
                s += c + ' '
            print(s)

            if not dryrun:
                #subprocess.check_call(cmdlist)
                proc = subprocess.Popen(cmdlist,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                stdout_data, stderr_data = proc.communicate()
                if proc.returncode != 0:
                    msg = '{} failed, '.format(cmdlist) + \
                          'status code {} '.format(proc.returncode) + \
                          'stdout {} '.format(stdout_data) + \
                          'stderr {}'.format(stderr_data)
                    print(msg)
                    return proc.returncode

        # Save the name of the object file so that they can all be linked
        # at the end
        objfiles.append(objfile)

    # Build the link command and then link
    print(('\nLinking object files to make {0}...'.format(os.path.basename(target))))
    cmd = fc + ' '
    cmdlist = []
    cmdlist.append(fc)
    for switch in compileflags:
        cmd += switch + ' '
        cmdlist.append(switch)
    cmdlist.append('-o')
    cmdlist.append(os.path.join('.', target))
    for objfile in objfiles:
        cmdlist.append(objfile)
    for switch in syslibs:
        cmdlist.append(switch)
    if not dryrun:
        s = ''
        for c in cmdlist:
            s += c + ' '
        print(s)
        #subprocess.check_call(cmdlist)
        proc = subprocess.Popen(cmdlist,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        stdout_data, stderr_data = proc.communicate()
        if proc.returncode != 0:
            msg = '{} failed, '.format(cmdlist) + \
                  'status code {} '.format(proc.returncode) + \
                  'stdout {} '.format(stdout_data) + \
                  'stderr {}'.format(stderr_data)
            print(msg)
            return proc.returncode

    # create makefile
    if makefile:
        create_makefile(target, srcdir, srcdir2, objfiles,
                        fc, compileflags, cc, cflags, syslibs,
                        modules=['-module '])

    # return
    return 0


def compile_with_ifort(srcfiles, target, cc, objdir_temp, moddir_temp,
                       expedite, dryrun, double, debug, fflagsu, arch,
                       srcdir, srcdir2, makefile):
    """
    Make target on Windows OS
    
    """
    # C/C++ compiler switches
    if debug:
        cflags = ['-O0', '-g']
    else:
        cflags = ['-O3']
    syslibs = ['-lc']

    fc = 'ifort.exe'
    cc = 'cl.exe'
    cflags = ['-nologo', '-c']
    fflags = ['-heap-arrays:0', '-fpe:0', '-traceback', '-nologo']
    if debug:
        fflags += ['-debug']
        cflags += ['-Zi']
    else:
        # production version compile flags
        fflags += ['-O2']
        cflags += ['-O2']
    if double:
        fflags.append('/real_size:64')
    if fflagsu is not None:
        t = fflagsu.split()
        for fflag in t:
            fflags.append('-'+fflag)
    objext = '.obj'
    batchfile = 'compile.bat'
    if os.path.isfile(batchfile):
        try:
            os.remove(batchfile)
        except:
            pass

    # Create target
    try:
        # clean exe prior to build so that test for exe below can return a
        # non-zero error code
        if flopy_avail:
            if flopy_is_exe(target):
                os.remove(target)
        makebatch(batchfile, fc, cc, fflags, cflags, srcfiles, target,
                  arch, objdir_temp, moddir_temp)
        #subprocess.check_call([batchfile, ])
        proc = subprocess.Popen([batchfile, ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        while True:
            line = proc.stdout.readline()
            c = line.decode('utf-8')
            if c != '':
                c = c.rstrip('\r\n')
                print('{}'.format(c))
            else:
                break
        if flopy_avail:
            if not flopy_is_exe(target):
                return 1
        else:
            return 0
    except:
        print('Could not make x64 target: ', target)

    # create makefile
    if makefile:
        print('makefile not created for Windows with Intel Compiler.')

    # return
    return 0


def makebatch(batchfile, fc, cc, compileflags, cflags, srcfiles, target, arch,
              objdir_temp, moddir_temp):
    '''
    Make an ifort batch file
    
    '''
    iflist = ['IFORT_COMPILER17', 'IFORT_COMPILER16', 'IFORT_COMPILER15',
              'IFORT_COMPILER14', 'IFORT_COMPILER13']
    found = False
    for ift in iflist:
        cpvars = os.environ.get(ift)
        if cpvars is not None:
            found = True
            break
    if not found:
        raise Exception('Pymake could not find IFORT compiler.')
    cpvars += os.path.join('bin', 'compilervars.bat')
    if not os.path.isfile(cpvars):
        raise Exception('Could not find cpvars: {0}'.format(cpvars))
    f = open(batchfile, 'w')
    line = 'call ' + '"' + os.path.normpath(cpvars) + '" ' + arch + '\n'
    f.write(line)

    # write commands to build object files
    for srcfile in srcfiles:
        if srcfile.endswith('.c') or srcfile.endswith('.cpp'):
            cmd = cc + ' '
            for switch in cflags:
                cmd += switch + ' '
            obj = os.path.join(objdir_temp,
                               os.path.splitext(os.path.basename(srcfile))[0]
                               + '.obj' )
            cmd += '-Fo' + obj + ' '
            cmd += srcfile
        else:
            cmd = fc + ' '
            for switch in compileflags:
                cmd += switch + ' '
            cmd += '-c' + ' '
            cmd += '/module:{0}\ '.format(moddir_temp)
            cmd += '/object:{0}\ '.format(objdir_temp)
            cmd += srcfile
            f.write('echo ' + os.path.basename(srcfile) + '\n')
        f.write(cmd + '\n')

    # write commands to link
    cmd = fc + ' '
    for switch in compileflags:
        cmd += switch + ' '
    cmd += '-o' + ' ' + target + ' ' + objdir_temp + '\*.obj' + '\n'
    f.write(cmd)
    f.close()
    return


def create_makefile(target, srcdir, srcdir2, objfiles,
                    fc, fflags, cc, cflags, syslibs,
                    objext='.o', modules=['-I', '-J']):
    # open makefile
    f = open('makefile', 'w')

    # write header for the make file
    f.write('# makefile created on {}\n'.format(datetime.datetime.now()) +
            '# by pymake (version {})\n'.format(__version__))
    f.write('# using the {} fortran and {} c/c++ compilers.\n'.format(fc, cc))
    f.write('\n')

    # specify directory for the executable
    f.write('# Define the directories for the object and module files,\n' +
            '# the executable, and the executable name and path.\n')
    pth = os.path.dirname(objfiles[0]).replace('\\', '/')
    f.write('OBJDIR = {}\n'.format(pth))
    pth = os.path.dirname(target).replace('\\', '/')
    if len(pth) < 1:
        pth = '.'
    f.write('BINDIR = {}\n'.format(pth))
    pth = target.replace('\\', '/')
    f.write('PROGRAM = {}\n'.format(pth))
    f.write('\n')
    dirs = [d[0] for d in os.walk(srcdir)]
    if srcdir2 is not None:
        dirs2 = [d[0] for d in os.walk(srcdir2)]
        dirs = dirs + dirs2
    srcdirs = []
    for idx, dir in enumerate(dirs):
        srcdirs.append('SOURCEDIR{}'.format(idx+1))
        line = '{}={}\n'.format(srcdirs[idx], dir)
        f.write(line)
    f.write('\n')
    f.write('VPATH = \\\n')
    for idx, sd in enumerate(srcdirs):
        f.write('${' + '{}'.format(sd) + '} ')
        if idx+1 < len(srcdirs):
            f.write('\\')
        f.write('\n')
    f.write('\n')

    ffiles = ['.f', '.f90', '.F90', '.fpp']
    cfiles = ['.c', '.cpp']
    line = '.SUFFIXES: '
    for tc in cfiles:
        line += '{} '.format(tc)
    for tf in ffiles:
        line += '{} '.format(tf)
    line += objext
    f.write('{}\n'.format(line))
    f.write('\n')

    f.write('# Define the Fortran compile flags\n')
    f.write('F90 = {}\n'.format(fc))
    line = 'F90FLAGS = '
    for ff in fflags:
        line += '{} '.format(ff)
    f.write('{}\n'.format(line))
    f.write('\n')

    f.write('# Define the C compile flags\n')
    f.write('CC = {}\n'.format(cc))
    line = 'CFLAGS = '
    for cf in cflags:
        line += '{} '.format(cf)
    f.write('{}\n'.format(line))
    f.write('\n')

    f.write('# Define the libraries\n')
    line = 'SYSLIBS = '
    for sl in syslibs:
        line += '{} '.format(sl)
    f.write('{}\n'.format(line))
    f.write('\n')

    f.write('OBJECTS = \\\n')
    for idx, objfile in enumerate(objfiles):
        f.write('$(OBJDIR)/{} '.format(os.path.basename(objfile)))
        if idx+1 < len(objfiles):
            f.write('\\')
        f.write('\n')
    f.write('\n')

    f.write('# Define task functions\n')
    f.write('\n')

    f.write('# Create the bin directory and compile and link the executable\n')
    all = os.path.splitext(os.path.basename(target))[0]
    f.write('all: makebin | {}\n'.format(all))
    f.write('\n')

    f.write('# Make the bin directory for the executable\n')
    f.write('makebin :\n')
    f.write('\tmkdir -p $(BINDIR)\n')
    f.write('\n')


    f.write('# Define the objects ' +
            'that make up {}\n'.format(os.path.basename(target)))
    f.write('{}: $(OBJECTS)\n'.format(all))
    line = '\t-$(F90) $(F90FLAGS) -o $(PROGRAM) $(OBJECTS) $(SYSLIBS) '
    for m in modules:
        line += '{}$(OBJDIR) '.format(m)
    f.write('{}\n'.format(line))
    f.write('\n')

    for tf in ffiles:
        f.write('$(OBJDIR)/%{} : %{}\n'.format(objext, tf))
        f.write('\t@mkdir -p $(@D)\n')
        line = '\t$(F90) $(F90FLAGS) -c $< -o $@ '
        for m in modules:
            line += '{}$(OBJDIR) '.format(m)
        f.write('{}\n'.format(line))
        f.write('\n')

    for tc in cfiles:
        f.write('$(OBJDIR)/%.o : %{}\n'.format(tc))
        f.write('\t@mkdir -p $(@D)\n')
        line = '\t$(CC) $(CFLAGS) -c $< -o $@'
        f.write('{}\n'.format(line))
        f.write('\n')

    f.write('# Clean the object and module files and the executable\n')
    f.write('.PHONY : clean\n' +
            'clean : \n' +
            '\t-rm -rf $(OBJDIR)\n' +
            '\t-rm -rf $(BINDIR)\n')
    f.write('\n')

    f.write('# Clean the object and module files\n')
    f.write('.PHONY : cleanobj\n' +
            'cleanobj : \n' +
            '\t-rm -rf $(OBJDIR)\n')
    f.write('\n')

    # close the make file
    f.close()


def main(srcdir, target, fc, cc, makeclean=True, expedite=False,
         dryrun=False, double=False, debug=False,
         include_subdirs=False, fflags=None, arch='intel64',
         makefile=False, srcdir2=None):
    '''
    Main part of program

    '''
    # initialize success
    success = 0

    # write summary information
    print('\nsource files are in: {0}'.format(srcdir))
    print('executable name to be created: {0}'.format(target))
    if srcdir2 is not None:
        print('additional source files are in: {}'.format(srcdir2))

    # make sure the path for the target exists
    pth = os.path.dirname(target)
    if pth == '':
        pth = '.'
    if not os.path.exists(pth):
        print('creating target path - {}'.format(pth))
        os.makedirs(pth)

    # initialize
    srcdir_temp, objdir_temp, moddir_temp = initialize(srcdir, target,
                                                       srcdir2)

    # get ordered list of files to compile
    srcfiles = get_ordered_srcfiles(srcdir_temp, include_subdirs)

    # compile with gfortran or ifort
    winifort = False
    if fc == 'gfortran':
        objext = '.o'
        create_openspec(srcdir_temp)
        success = compile_with_gnu(srcfiles, target, cc,
                                   objdir_temp, moddir_temp,
                                   expedite, dryrun, double, debug, fflags,
                                   srcdir, srcdir2, makefile)
    elif fc == 'ifort':
        platform = sys.platform
        if platform.lower() == 'darwin':
            create_openspec(srcdir_temp)
            objext = '.o'
            success = compile_with_mac_ifort(srcfiles, target, cc,
                                             objdir_temp, moddir_temp,
                                             expedite, dryrun, double,
                                             debug, fflags,
                                             srcdir, srcdir2, makefile)
        else:
            winifort = True
            objext = '.obj'
            cc = 'cl.exe'
            success = compile_with_ifort(srcfiles, target, cc,
                                         objdir_temp, moddir_temp,
                                         expedite, dryrun, double, debug,
                                         fflags, arch,
                                         srcdir, srcdir2, makefile)
    else:
        raise Exception('Unsupported compiler')

    # Clean it up
    if makeclean:
        clean(srcdir_temp, objdir_temp, moddir_temp, objext, winifort)
        
    return success


if __name__ == "__main__":
    # get the arguments
    args = parser()

    # call main -- note that this form allows main to be called
    # from python as a function.
    main(args.srcdir, args.target, args.fc, args.cc, args.makeclean,
         args.expedite, args.dryrun, args.double, args.debug,
         args.subdirs, args.fflags, args.arch, args.makefile,
         args.commonsrc)
