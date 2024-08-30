#-------------------------------------------------------------------------------
#   android-create-apk.py
#
#   Helper script to create an APK project directory and create
#   an APK.
#
#   The Android SDK is expected under "fips-sdks/android/"
#
#   Arguments:
#
#   --path      the current cmake binary dir (where the .so file resides)
#   --deploy    path where the .apk file will be copied to
#   --name      the target name (result will be target.apk)
#   --abi       "armeabi-v7a", "mips" or "x86" (default is armeabi-v7a)
#   --version   the Android SDK platform version (default is "28")
#   --package   the APK main package name (e.g. org.fips.bla)
#
import sys
import os
import argparse
import shutil
import subprocess
from pathlib import Path
import platform

fips_dir = os.path.normpath(os.path.dirname(os.path.abspath(__file__)) + '/..')
SDK_HOME = os.path.abspath(fips_dir + '/../fips-sdks/android/') + '/'
BUILD_TOOLS = SDK_HOME + 'build-tools/35.0.0/'
EXE = '.exe' if platform.system() == 'Windows' else ''
BAT = '.bat' if platform.system() == 'Windows' else ''
AAPT = BUILD_TOOLS + 'aapt' + EXE
D8 = BUILD_TOOLS + 'd8' + BAT
ZIPALIGN = BUILD_TOOLS + 'zipalign' + EXE
APKSIGNER = BUILD_TOOLS + 'apksigner' + BAT
MIN_VERSION = 21

if not os.path.isdir(SDK_HOME):
    print("Can't find Android SDK '{}'!".format(SDK_HOME))
    sys.exit(10)
for tool in [AAPT, D8, ZIPALIGN, APKSIGNER]:
    if not os.path.isfile(tool):
        print("Can't find required tool in Android SDK: {}".format(tool))
        sys.exit(10)

parser = argparse.ArgumentParser(description="Android APK package helper.")
parser.add_argument('--path', help='path to the cmake build dir', required=True)
parser.add_argument('--deploy', help='path where resulting APK will be copied to', required=True)
parser.add_argument('--name', help='cmake target name', required=True)
parser.add_argument('--abi', help='the NDK ABI string (armeabi-v7a, mips or x86', default='armeabi-v7a')
parser.add_argument('--version', help='the Android SDK platform version (e.g. 28)', default='28')
parser.add_argument('--package', help='the Java package name', required=True)
args = parser.parse_args()

if not args.path.endswith('/'):
    args.path += '/'
if not args.deploy.endswith('/'):
    args.deploy += '/'
if not os.path.exists(args.deploy):
    os.makedirs(args.deploy)

pkg_name = args.package.replace('-','_')

# create the empty project
apk_dir = args.path + 'android/' + args.name + '/'
if not os.path.exists(apk_dir):
    os.makedirs(apk_dir)
libs_dir = apk_dir + 'lib/' + args.abi + '/'
if not os.path.exists(libs_dir):
    os.makedirs(libs_dir)
src_dir = apk_dir + 'src/' + pkg_name.replace('.', '/')
if not os.path.exists(src_dir):
    os.makedirs(src_dir)
obj_dir = apk_dir + '/obj'
if not os.path.exists(obj_dir):
    os.makedirs(obj_dir)
bin_dir = apk_dir + '/bin'
if not os.path.exists(bin_dir):
    os.makedirs(bin_dir)

# copy the native shared library
so_name = 'lib' + args.name + '.so'
src_so = args.path + so_name
dst_so = libs_dir + so_name
shutil.copy(src_so, dst_so)

# copy the dummy assets directory
res_dir = apk_dir + 'res/'
if not os.path.exists(res_dir):
    shutil.copytree(fips_dir + '/templates/android_assets/res', res_dir)

# generate AndroidManifest.xml
with open(apk_dir + 'AndroidManifest.xml', 'w') as f:
    f.write('<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n')
    f.write('  package="{}"\n'.format(pkg_name))
    f.write('  android:versionCode="1"\n')
    f.write('  android:versionName="1.0">\n')
    f.write('  <uses-sdk android:minSdkVersion="{}" android:targetSdkVersion="{}"/>\n'.format(MIN_VERSION, args.version))
    f.write('  <uses-permission android:name="android.permission.INTERNET"></uses-permission>\n')
    f.write('  <uses-feature android:glEsVersion="0x00030000"></uses-feature>\n')
    f.write('  <application android:label="{}" android:debuggable="true" android:hasCode="false">\n'.format(args.name))
    f.write('    <activity android:name="android.app.NativeActivity"\n');
    f.write('      android:label="{}"\n'.format(args.name))
    f.write('      android:launchMode="singleTask"\n')
    f.write('      android:exported="true"\n')
    f.write('      android:screenOrientation="fullUser"\n')
    f.write('      android:configChanges="orientation|screenSize|keyboard|keyboardHidden">\n')
    f.write('      <meta-data android:name="android.app.lib_name" android:value="{}"/>\n'.format(args.name))
    f.write('      <intent-filter>\n')
    f.write('        <action android:name="android.intent.action.MAIN"/>\n')
    f.write('        <category android:name="android.intent.category.LAUNCHER"/>\n')
    f.write('      </intent-filter>\n')
    f.write('    </activity>\n')
    f.write('  </application>\n')
    f.write('</manifest>\n')

# prepare APK structure
cmd = [
    AAPT,
    'package',
    '-v', '-f', '-m',
    '-S', 'res', '-J', 'src',
    '-M', 'AndroidManifest.xml',
    '-I', SDK_HOME + 'platforms/android-' + args.version + '/android.jar'
]
subprocess.call(cmd, cwd=apk_dir)

# compile Java sources
cmd = [
    'javac', '-d', './obj',
    '-classpath', SDK_HOME + 'platforms/android-' + args.version + '/android.jar',
    '-sourcepath', 'src',
    '-source', '17',
    '-target', '17',
    src_dir + '/R.java'
]
subprocess.call(cmd, cwd=apk_dir)

# d8/r8, see https://r8.googlesource.com/r8/+/refs/heads/main/README.md
# convert Java byte code to DEX
cmd = [
    D8
] + list(Path(apk_dir + '/obj').rglob('*.class')) + [
    '--release',
    '--min-api', '{}'.format(MIN_VERSION),
    '--output', './bin',
    #'--lib', SDK_HOME + 'platforms/android-' + args.version + '/android.jar'
]
subprocess.call(cmd, cwd=apk_dir)

# package the APK
cmd = [
    AAPT,
    'package',
    '-v', '-f',
    '-S', 'res',
    '-M', 'AndroidManifest.xml',
    '-I', SDK_HOME + 'platforms/android-' + args.version + '/android.jar',
    '-F', args.path + args.name + '-unaligned.apk',
    'bin'
]
subprocess.call(cmd, cwd=apk_dir)
cmd = [
    AAPT, 'add', '-v',
    args.path + args.name + '-unaligned.apk',
    'lib/'+args.abi+'/'+so_name
]
subprocess.call(cmd, cwd=apk_dir)

# run zipalign on the package
cmd = [
    ZIPALIGN,
    '-f', '4',
    args.path + args.name + '-unaligned.apk',
    args.path + args.name + '.apk'
]
subprocess.call(cmd, cwd=apk_dir)

# create debug signing key
keystore_path = args.path + 'debug.keystore'
if not os.path.exists(keystore_path):
    cmd = [
        'keytool', '-genkeypair',
        '-keystore', keystore_path,
        '-storepass', 'android',
        '-alias', 'androiddebugkey',
        '-keypass', 'android',
        '-keyalg', 'RSA',
        '-validity', '10000',
        '-dname', 'CN=,OU=,O=,L=,S=,C='
    ]
    subprocess.call(cmd, cwd=apk_dir)

# sign the APK
cmd = [
    APKSIGNER, 'sign',
    '-v',
    '--ks', keystore_path,
    '--ks-pass', 'pass:android',
    '--key-pass', 'pass:android',
    '--ks-key-alias', 'androiddebugkey',
    args.path + args.name + '.apk'
]
subprocess.call(cmd, cwd=apk_dir)

# verify the APK
cmd = [
    APKSIGNER, 'verify',
    '-v',
    args.path + args.name + '.apk'
]
subprocess.call(cmd, cwd=apk_dir)

# copy APK to the fips-deploy directory
shutil.copy(args.path+args.name+'.apk', args.deploy+args.name+'.apk')
