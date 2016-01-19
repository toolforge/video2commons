#! /usr/bin/python
# -*- coding: UTF-8 -*-
#
# Job for web video transcode
#
# Support two modes
# 1) non-free media transcode (delays the media file being inserted,
#    adds note to talk page once ready)
# 2) derivatives for video (makes new sources for the asset)
#
# @adaptedfrom https://github.com/wikimedia/mediawiki-extensions-TimedMediaHandler/blob/master/WebVideoTranscode/WebVideoTranscodeJob.php under GPLv2
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General License for more details.
#
# You should have received a copy of the GNU General License
# along with self program.  If not, see <http://www.gnu.org/licenses/>
# 

import os, sys
import time
import subprocess
from transcode import WebVideoTranscode
from transferstatus import TransferStatus
from globals import * # all variables and functions starting with "wg" and "wf"

class WebVideoTranscodeJob(object):
    def __init__(self, source, target, key, statuscallback = None, errorcallback = None):
        #super(WebVideoTranscodeJob, self).__init__('webVideoTranscode', title, key, id)
        self.source = os.path.abspath(source)
        self.target = os.path.abspath(target)
        self.key = key
        self.statuscallback = statuscallback or (lambda text, percent: None)
        self.errorcallback = errorcallback or (lambda text: None)
        self.removeDuplicates = True

    def output(self, msg):
        """
        Local method to debug output (jobs don't have access to the maintenance output class)
        @param msg string
        """
        msg = msg.strip()
        self.statuscallback(msg, None)
        print msg

    def getFile(self):
        """
        @return File
        """
        if not hasattr(self, 'file'):
            self.file = open(self.source, 'r')
        return self.file

    def getTargetEncodePath(self):
        """
        @return string
        """
        if not hasattr(self, 'targetEncodeFile'):
            self.targetEncodeFile = open(self.target, 'w')

        return self.targetEncodeFile.name

    def getSourceFilePath(self):
        """
        @return string|bool
        """
        if not hasattr(self, 'sourceFilePath'):
            self.sourceFilePath = self.getFile().name

        return self.sourceFilePath

    def setError(self, error, transcodeKey = None):
        """
        Update the transcode table with failure time and error
        @param transcodeKey string
        @param error string
        """
        self.errorcallback(error)

    def run(self):
        """
        Run the transcode request
        @return boolean success
        """
        #global wgFFmpeg2theoraLocation
        # get a local pointer to the file
        file = self.getFile()

        # Validate the file exists:
        if not file:
            self.setError(self.source + ': File not found ')
            return False


        # Validate the transcode key param:
        transcodeKey = self.key
        # Build the destination target
        if not transcodeKey in WebVideoTranscode.derivativeSettings:
            error = "Transcode key transcodeKey not found, skipping"
            self.setError(error)
            return False


        # Validate the source exists:
        if not self.getSourceFilePath() or not os.path.isfile(self.getSourceFilePath()):
            status = self.source + ': Source not found ' + self.getSourceFilePath()
            self.setError(status, transcodeKey)
            return False


        options = WebVideoTranscode.derivativeSettings[transcodeKey]

        if 'novideo' in options:
            self.output("Encoding to audio codec: " + options['audioCodec'])
        else:
            self.output("Encoding to codec: " + options['videoCodec'])

        # Check the codec see which encode method to call
        if 'novideo' in options:
            status = self.ffmpegEncode(options)
        elif options['videoCodec'] == 'theora' and wgFFmpeg2theoraLocation != False:
            status = self.ffmpeg2TheoraEncode(options)
        elif options['videoCodec'] in ['vp8', 'vp9', 'h264'] or \
                (options['videoCodec'] == 'theora' and wgFFmpeg2theoraLocation == False):
            # Check for twopass:
            if 'twopass' in options and options['twopass'] == 'True':
                # ffmpeg requires manual two pass
                status = self.ffmpegEncode(options, 1)
                if status and not isinstance(status, basestring):
                    status = self.ffmpegEncode(options, 2)
            else:
                status = self.ffmpegEncode(options)
        else:
            self.output('Error unknown codec:' + options['videoCodec'])
            status = 'Error unknown target encode codec:' + options['videoCodec']

        # Remove any log files,
        # all useful info should be in status and or we are done with 2 passs encoding
        self.removeFfmpegLogFiles()

        # If status is oky and target does not exist, reset status
        if status == True and not os.path.isfile(self.getTargetEncodePath()):
            status = 'Target does not exist: ' + self.getTargetEncodePath()

        # If status is ok and target is larger than 0 bytes
        if status == True and os.path.getsize(self.getTargetEncodePath()) > 0:
            pass # Done
        else:
            # Update the transcode table with failure time and error
            self.setError(status, transcodeKey)

        return status == True


    def removeFfmpegLogFiles(self):
        path =  self.getTargetEncodePath()
        dir = os.path.dirname(path.rstrip(os.pathsep))
        if os.path.isdir(dir):
            for file in os.listdir(dir):
                log_path = os.path.abspath(dir + "/" + file)
                ext = file.split('.')[-1]
                if ext == 'log' and log_path.startswith(path):
                    os.unlink(log_path)

    def ffmpegEncode(self, options, p=0):
        """
        Utility helper for ffmpeg and ffmpeg2theora mapping
        @param options array
        @param p int
        @return bool|string
        """
        #global wgFFmpegLocation, wgTranscodeBackgroundMemoryLimit

        if not os.path.isfile(self.getSourceFilePath()):
            return "source file is missing, " + self.getSourceFilePath() + ". Encoding failed."


        # Set up the base command
        #cmd = wfEscapeShellArg(wgFFmpegLocation) + ' -y -i ' + wfEscapeShellArg(self.getSourceFilePath())
        cmd = wfEscapeShellArg(wgFFmpegLocation) + ' -y -i -' # Tracking

        if 'vpre' in options:
            cmd += ' -vpre ' + wfEscapeShellArg(options['vpre'])

        if 'novideo' in options:
            cmd += " -vn "
        elif options['videoCodec'] == 'vp8' or options['videoCodec'] == 'vp9':
            cmd += self.ffmpegAddWebmVideoOptions(options, p)
        elif options['videoCodec'] == 'h264':
            cmd += self.ffmpegAddH264VideoOptions(options, p)
        elif options['videoCodec'] == 'theora':
            cmd += self.ffmpegAddTheoraVideoOptions(options, p)

        # Add size options:
        #cmd += self.ffmpegAddVideoSizeOptions(options)

        # Check for start time
        if 'starttime' in options:
            cmd += ' -ss ' + wfEscapeShellArg(options['starttime'])
        else:
            options['starttime'] = 0

        # Check for end time:
        if 'endtime' in options:
            cmd += ' -t ' + str(options['endtime'])  - str(options['starttime'])


        if p == 1 or 'noaudio' in options:
            cmd += ' -an'
        else:
            cmd += self.ffmpegAddAudioOptions(options, p)


        if p != 0:
            cmd += " -pass " + wfEscapeShellArg(p)
            cmd += " -passlogfile " + wfEscapeShellArg(self.getTargetEncodePath() + '.log')

        # And the output target:
        if p == 1:
            cmd += ' /dev/null'
        else:
            cmd += " " + wfEscapeShellArg(self.getTargetEncodePath())


        self.output("Running cmd: \n\n" + cmd + "\n")

        # Right before we output remove the old file
        retval, shellOutput = self.runShellExec(cmd)

        if retval != 0:
            return cmd + \
                "\n\nExitcode: " + str(retval) + "\nMemory: " + str(wgTranscodeBackgroundMemoryLimit) + "\n\n" + \
                shellOutput

        return True


    def ffmpegAddH264VideoOptions(self, options, p):
        """
        Adds ffmpeg shell options for h264
        
        @param options
        @param p
        @return string
        """
        #global wgFFmpegThreads
        # Set the codec:
        cmd = " -threads " + str(wgFFmpegThreads) + " -vcodec libx264"
        # Check for presets:
        if 'preset' in options:
            # Add the two vpre types:
            if options['preset'] == 'ipod320':
                # @codingStandardsIgnoreStart
                cmd += " -profile:v baseline -preset slow -coder 0 -bf 0 -weightb 1 -level 13 -maxrate 768k -bufsize 3M"
                # @codingStandardsIgnoreEnd
            elif options['preset'] in ['720p', 'ipod640']:
                # @codingStandardsIgnoreStart
                cmd += " -profile:v baseline -preset slow -coder 0 -bf 0 -refs 1 -weightb 1 -level 31 -maxrate 10M -bufsize 10M"
                # @codingStandardsIgnoreEnd
            else:
                # in the default case just pass along the preset to ffmpeg
                cmd += " -vpre " + wfEscapeShellArg(options['preset'])

        if 'videoBitrate' in options:
            cmd += " -b " + wfEscapeShellArg(options['videoBitrate'])

        # Output mp4
        cmd += " -f mp4"
        return cmd


    def ffmpegAddVideoSizeOptions(self, options):
        cmd = ''
        # Get a local pointer to the file object
        file = self.getFile()

        # Check for aspect ratio (we don't do anything with self right now)
        if 'aspect' in options:
            aspectRatio = options['aspect']
        else:
            aspectRatio = file.getWidth() + ':' + file.getHeight()

        if 'maxSize' in options:
            # Get size transform (if maxSize is > file, file size is used:

            width, height = WebVideoTranscode.getMaxSizeTransform(file, options['maxSize'])
            cmd += ' -s ' + str(width) + 'x' + str(height)
        elif ('width' in options and options['width'] > 0) and \
            ('height' in options and options['height'] > 0):
            cmd += ' -s ' + str(options['width']) + 'x' + str(options['height'])


        # Handle crop:
        optionMap = {
            'cropTop': '-croptop',
            'cropBottom': '-cropbottom',
            'cropLeft': '-cropleft',
            'cropRight': '-cropright'
        }
        for name, cmdArg in optionMap.items():
            if name in options:
                cmd += " " + cmdArg + " " + wfEscapeShellArg(options[name])

        return cmd

    def ffmpegAddWebmVideoOptions(self, options, p):
        """
        Adds ffmpeg shell options for webm
        
        @param options
        @param p
        @return string
        """
        #global wgFFmpegThreads

        # Get a local pointer to the file object
        file = self.getFile()

        cmd =' -threads ' + str(wgFFmpegThreads)

        # check for presets:
        if 'preset' in options:
            if options['preset'] == "360p":
                cmd += " -vpre libvpx-360p"
            elif options['preset'] == "720p":
                cmd += " -vpre libvpx-720p"
            elif options['preset'] == "1080p":
                cmd += " -vpre libvpx-1080p"


        # Add the boiler plate vp8 ffmpeg command:
        cmd += " -skip_threshold 0 -bufsize 6000k -rc_init_occupancy 4000"

        # Check for video quality:
        if 'videoQuality' in options and options['videoQuality'] >= 0:
            # Map 0-10 to 63-0, higher values worse quality
            quality = 63 - int(int(options['videoQuality']) / 1063)
            cmd += " -qmin " + wfEscapeShellArg(quality)
            cmd += " -qmax " + wfEscapeShellArg(quality)


        # Check for video bitrate:
        if 'videoBitrate' in options:
            cmd += " -qmin 1 -qmax 51"
            cmd += " -vb " + wfEscapeShellArg(options['videoBitrate'] * 1000)

        # Set the codec:
        if options['videoCodec'] == 'vp9':
            cmd += " -vcodec libvpx-vp9"
            if 'tileColumns' in options:
                cmd += ' -tile-columns ' + wfEscapeShellArg(options['tileColumns'])
        else:
            cmd += " -vcodec libvpx"


        # Check for keyframeInterval
        if 'keyframeInterval' in options:
            cmd += ' -g ' + wfEscapeShellArg(options['keyframeInterval'])
            cmd += ' -keyint_min ' + wfEscapeShellArg(options['keyframeInterval'])

        if 'deinterlace' in options:
            cmd += ' -deinterlace'


        # Output WebM
        cmd += " -f webm"

        return cmd



    def ffmpegAddTheoraVideoOptions(self, options, p):
        """
        Adds ffmpeg/avconv shell options for ogg
        
        Used only when wgFFmpeg2theoraLocation set to False.
        Warning: does not create Ogg skeleton metadata track.
        
        @param options
        @param p
        @return string
        """
        #global wgFFmpegThreads

        # Get a local pointer to the file object
        file = self.getFile()

        cmd = ' -threads ' + str(wgFFmpegThreads)

        # Check for video quality:
        if 'videoQuality' in options and options['videoQuality'] >= 0:
            # Map 0-10 to 63-0, higher values worse quality
            quality = 63 - int(int(options['videoQuality']) / 1063)
            cmd += " -qmin " + wfEscapeShellArg(quality)
            cmd += " -qmax " + wfEscapeShellArg(quality)


        # Check for video bitrate:
        if 'videoBitrate' in options:
            cmd += " -qmin 1 -qmax 51"
            cmd += " -vb " + wfEscapeShellArg(options['videoBitrate'] * 1000)

        # Set the codec:
        cmd += " -vcodec theora"

        # Check for keyframeInterval
        if 'keyframeInterval' in options:
            cmd += ' -g ' + wfEscapeShellArg(options['keyframeInterval'])
            cmd += ' -keyint_min ' + wfEscapeShellArg(options['keyframeInterval'])

        if 'deinterlace' in options:
            cmd += ' -deinterlace'

        if 'framerate' in options:
            cmd += ' -r ' + wfEscapeShellArg(options['framerate'])


        # Output Ogg
        cmd += " -f ogg"

        return cmd


    def ffmpegAddAudioOptions(self, options, p):
        """
        @param options array
        @param p
        @return string
        """
        cmd = ''
        if 'audioQuality' in options:
            cmd += " -aq " + wfEscapeShellArg(options['audioQuality'])

        if 'audioBitrate' in options:
            cmd += ' -ab ' + str(options['audioBitrate']) * 1000

        if 'samplerate' in options:
            cmd += " -ar " +  wfEscapeShellArg(options['samplerate'])

        if 'channels' in options:
            cmd += " -ac " + wfEscapeShellArg(options['channels'])


        if 'audioCodec' in options:
            encoders = {
                'vorbis': 'libvorbis',
                'opus': 'libopus',
                'mp3': 'libmp3lame',
            }
            if options['audioCodec'] in encoders:
                codec = encoders[options['audioCodec']]
            else:
                codec = options['audioCodec']

            cmd += " -acodec " + wfEscapeShellArg(codec)
            if codec == 'aac':
                # the aac encoder is currently "experimental" in libav 9? :P
                cmd += ' -strict experimental'
        else:
            # if no audio codec set use vorbis :
            cmd += " -acodec libvorbis "

        return cmd


    def ffmpeg2TheoraEncode(self, options):
        """
        ffmpeg2Theora mapping is much simpler since it is the basis of the the firefogg API
        @param options array
        @return bool|string
        """
        #global wgFFmpeg2theoraLocation, wgTranscodeBackgroundMemoryLimit

        if not os.path.isfile(self.getSourceFilePath()):
            return "source file is missing, " + self.getSourceFilePath() + ". Encoding failed."

        # Set up the base command
        cmd = wfEscapeShellArg(wgFFmpeg2theoraLocation) + ' ' + wfEscapeShellArg(self.getSourceFilePath())

        file = self.getFile()

        if 'maxSize' in options:
            width, height = WebVideoTranscode.getMaxSizeTransform(file, options['maxSize'])
            options['width'] = width
            options['height'] = height
            options['aspect'] = width + ':' + height
            del options['maxSize']


        # Add in the encode settings
        for key, val in options.items():
            if key in self.foggMap:
                if isinstance(self.foggMap[key], list):
                    cmd += ' ' + ' '.join(self.foggMap[key])
                elif val == 'True' or val == True:
                    cmd += ' ' + self.foggMap[key]
                elif val == 'False' or val == False:
                    # ignore "False" flags
                    pass
                else:
                    # normal get/set value
                    cmd += ' ' + self.foggMap[key] + ' ' + wfEscapeShellArg(val)


        # Add the output target:
        outputFile = self.getTargetEncodePath()
        cmd += ' -o ' + wfEscapeShellArg(outputFile)

        self.output("Running cmd: \n\n" + cmd + "\n")

        retval = 0
        retval, shellOutput = self.runShellExec(cmd)

        # ffmpeg2theora returns 0 status on some errors, so also check for file
        if retval != 0 or not os.path.isfile(outputFile) or os.path.getsize(outputFile) == 0:
            return cmd + \
                "\n\nExitcode: " + retval + "\nMemory: " + wgTranscodeBackgroundMemoryLimit + "\n\n" + \
                shellOutput

        return True


    def runShellExec(self, cmd):
        """
        Runs the shell exec command.
        if wgEnableBackgroundTranscodeJobs is enabled will mannage a background transcode task
        else it just directly passes off to wfShellExec
        
        @param cmd String Command to be run
        @return int, string
        """
        #global wgTranscodeBackgroundTimeLimit,
        #    wgTranscodeBackgroundMemoryLimit,
        #    wgTranscodeBackgroundSizeLimit,
        #    wgEnableNiceBackgroundTranscodeJobs

        # For profiling
        #caller = wfGetCaller()

        # Check if background tasks are enabled
        if wgEnableNiceBackgroundTranscodeJobs == False:
            # !!!
            return 'wgEnableNiceBackgroundTranscodeJobs enforced'
            # Directly execute the shell command:
            #limits = {
            #    "filesize": wgTranscodeBackgroundSizeLimit,
            #    "memory": wgTranscodeBackgroundMemoryLimit,
            #    "time": wgTranscodeBackgroundTimeLimit
            #}
            #return wfShellExec(cmd + ' 2>&1', retval, [], limits,
            #    { 'profileMethod': caller })


        encodingLog = self.getTargetEncodePath() + '.stdout.log'
        retvalLog = self.getTargetEncodePath() + '.retval.log'
        # Check that we can actually write to these files
        # (no point in running the encode if we can't write)
        #wfSuppressWarnings()
        try:
            open(encodingLog, 'a').close()
            open(retvalLog, 'a').close()
        except:
            #wfRestoreWarnings()
            return 1, "Error could not write to target location"

        #wfRestoreWarnings()

        # Fork out a process for running the transcode
        try:
            pid = os.fork()
        except OSError:
            errorMsg = 'wgEnableNiceBackgroundTranscodeJobs enabled but failed os.fork'
            self.output(errorMsg)
            return 1, errorMsg
        else:
            if pid == 0:
                # we are the child
                retval = self.runChildCmd(cmd, encodingLog, retvalLog)
                # dont remove any temp files in the child process, self is done
                # once the parent is finished
                #self.targetEncodeFile.preserve()
                #if self.source instanceof TempFSFile:
                #    self.source.preserve()

                # exit with the same code as the transcode:
                exit(retval)
            else:
                # we are the parent monitor and return status
                return self.monitorTranscode(pid, encodingLog, retvalLog)


    def runChildCmd(self, cmd, encodingLog, retvalLog):
        """
        @param cmd
        @param encodingLog
        @param retvalLog
        """
        #global wgTranscodeBackgroundTimeLimit, wgTranscodeBackgroundMemoryLimit,
        #wgTranscodeBackgroundSizeLimit

        # In theory we should use pcntl_exec but not sure how to get the stdout, ensure
        # we don't max php memory with the same protections provided by wfShellExec.

        # pcntl_exec requires a direct path to the exe and arguments as an array:
        # cmd = explode(' ', cmd)
        # baseCmd = array_shift(cmd)
        # print "run:" + baseCmd + " args: " + print_r(cmd, True)
        # status  = pcntl_exec(baseCmd , cmd)

        # Directly execute the shell command:
        # global wgTranscodeBackgroundPriority
        # status =
        # wfShellExec('nice -n ' + wgTranscodeBackgroundPriority + ' ' + cmd + ' 2>&1', retval)
        #limits = {
        #    "filesize": wgTranscodeBackgroundSizeLimit,
        #    "memory": wgTranscodeBackgroundMemoryLimit,
        #    "time": wgTranscodeBackgroundTimeLimit
        #}
        #retval, status = wfShellExec(cmd + ' 2>&1', [], limits,
        #    { 'profileMethod': caller })
        cmd = 'ulimit -f ' + wfEscapeShellArg(wgTranscodeBackgroundSizeLimit) + ';' + \
            'ulimit -v ' + wfEscapeShellArg(wgTranscodeBackgroundMemoryLimit) + ';' + \
            'ulimit -t ' + wfEscapeShellArg(wgTranscodeBackgroundTimeLimit) + ';' + \
            'nice -n ' + wfEscapeShellArg(wgTranscodeBackgroundPriority) + ' ' + cmd + ' 2>&1'

        log = open(encodingLog, 'w')
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=None, shell=True)
        status = TransferStatus(self.getFile(), process.stdin, os.path.getsize(self.getSourceFilePath()))
        status.start()
        percentage = -1
        while process.poll() is None:
            if status.status != percentage:
                percentage = status.status
                self.statuscallback(None, percentage)

            time.sleep(5)

        # Output the status:
        #wfSuppressWarnings()
        log.close()
        # Output the retVal to the retvalLog
        retval = process.returncode
        open(retvalLog, 'w').write(str(retval))
        #wfRestoreWarnings()

        return retval


    def monitorTranscode(self, pid, encodingLog, retvalLog):
        """
        @param pid
        @param retval
        @param encodingLog
        @param retvalLog
        @return string
        """
        #global wgTranscodeBackgroundTimeLimit, wgLang
        errorMsg = ''
        loopCount = 0
        oldFileSize = 0
        startTime = int(time.time())
        fileIsNotGrowing = False

        status = os.waitpid( pid, os.WNOHANG or os.WUNTRACED )[1]
        self.output("Encoding with pid: " + str(pid) + " \nos.waitpid: " + str(status) +
            "\nisProcessRunning: " + str(self.isProcessRunningKillZombie(pid)) + "\n")

        # Check that the child process is still running
        # (note this does not work well with  pcntl_waitpid for some reason :()
        while self.isProcessRunningKillZombie(pid):
            # self.output("pid is running")

            # Check that the target file is growing (every 5 seconds)
            if loopCount == 10:
                # only run check if we are outputing to target file
                # (two pass encoding does not output to target on first pass)
                #clearstatcache()
                newFileSize = os.path.getsize(self.getTargetEncodePath()) if os.path.isfile(self.getTargetEncodePath()) else 0
                # Don't start checking for file growth until we have an initial positive file size:
                if newFileSize > 0:
                    self.output(wfFormatSize(newFileSize) + ' Total size, encoding ' +
                        wfFormatSize((newFileSize - oldFileSize) / 5) + ' per second')
                    if newFileSize == oldFileSize:
                        if fileIsNotGrowing:
                            errorMsg = "Target File is not increasing in size, kill process."
                            self.output(errorMsg)
                            # file is not growing in size, kill proccess
                            retval = 1

                            # posix_kill(pid, 9)
                            self.killProcess(pid)
                            break

                        # Wait an additional 5 seconds of the file not growing to confirm
                        # the transcode is frozen.
                        fileIsNotGrowing = True
                    else:
                        fileIsNotGrowing = False

                    oldFileSize = newFileSize

                # reset the loop counter
                loopCount = 0


            # Check if we have global job run-time has been exceeded:
            if wgTranscodeBackgroundTimeLimit and int(time.time()) - startTime  > wgTranscodeBackgroundTimeLimit:
                errorMsg = "Encoding exceeded max job run time (" \
                    + wfFormatTimeHMS(wgTranscodeBackgroundTimeLimit) + "), kill process."
                self.output(errorMsg)
                # File is not growing in size, kill proccess
                retval = 1
                # posix_kill(pid, 9)
                self.killProcess(pid)
                break


            # Sleep for one second before repeating loop
            loopCount += 1
            time.sleep(1)


        returnPcntl = os.WEXITSTATUS(status)
        # check status
        #wfSuppressWarnings()
        returnCodeFile = open(retvalLog)
        #wfRestoreWarnings()

        # File based exit code seems more reliable than pcntl_wexitstatus
        retval = returnCodeFile.read(20)
        returnCodeFile.close()

        # return the encoding log contents (will be inserted into error table if an error)
        # (will be ignored and removed if success)
        if errorMsg != '':
            errorMsg +="\n\n"

        return retval, errorMsg + open(encodingLog).read(1000)

    @classmethod
    def isProcessRunningKillZombie(cls, pid):
        """
        check if proccess is running and not a zombie
        @param pid int
        @return bool
        """
        try:
            processState = subprocess.check_output(["/bin/ps", str(pid)]).split("\n")
        except subprocess.CalledProcessError:
            return False
        if len(processState) < 2:
            return False

        if '<defunct>' in processState[1]:
            # posix_kill(pid, 9)
            cls.killProcess(pid)
            return False

        return True

    @staticmethod
    def killProcess(pid):
        """
        Kill Application PID

        @param pid int
        @return bool
        """
        os.system("/bin/kill -9 " + str(pid))
        try:
            processState = subprocess.check_output(["/bin/ps", str(pid)]).split("\n")
        except subprocess.CalledProcessError:
            return False
        if len(processState) < 2:
            return False

        return True

    """
    Mapping between firefogg api and ffmpeg2theora command line
    
    This lets us share a common api between firefogg and WebVideoTranscode
    also see: http://firefogg.org/dev/index.html
    """
    foggMap = {
        # video
        'width':          "--width",
        'height':         "--height",
        'maxSize':        "--max_size",
        'noUpscaling':    "--no-upscaling",
        'videoQuality': "-v",
        'videoBitrate':   "-V",
        'twopass':        "--two-pass",
        'optimize':       "--optimize",
        'framerate':      "-F",
        'aspect':         "--aspect",
        'starttime':      "--starttime",
        'endtime':        "--endtime",
        'cropTop':        "--croptop",
        'cropBottom':     "--cropbottom",
        'cropLeft':       "--cropleft",
        'cropRight':      "--cropright",
        'keyframeInterval': "--keyint",
        'denoise':        ["--pp", "de"],
        'deinterlace':    "--deinterlace",
        'novideo':        ["--novideo", "--no-skeleton"],
        'bufDelay':       "--buf-delay",
        # audio
        'audioQuality':   "-a",
        'audioBitrate':   "-A",
        'samplerate':     "-H",
        'channels':       "-c",
        'noaudio':        "--noaudio",
        # metadata
        'artist':         "--artist",
        'title':          "--title",
        'date':           "--date",
        'location':       "--location",
        'organization':   "--organization",
        'copyright':      "--copyright",
        'license':        "--license",
        'contact':        "--contact"
    }
