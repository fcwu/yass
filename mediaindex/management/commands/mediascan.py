from django.core.management.base import BaseCommand
from django.conf import settings
from optparse import make_option
from os import walk, path, stat
from logging import getLogger
from subprocess import Popen, PIPE
from datetime import datetime
from mediaindex.models import MediaFile
from django.utils.timezone import utc

logger = getLogger(__name__)


class NotMediaFileException(Exception):
    pass


class MediaInfoNoVideoStreamException(Exception):
    pass


class MediaInfoNoGeneralStreamException(Exception):
    pass


class InternalException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class Command(BaseCommand):
    help = 'Media indexing service'
    option_list = BaseCommand.option_list + (
        make_option('--nodaemon',
                    action='store_false',
                    dest='daemon',
                    default=True,
                    help='Not to run as daemon'),
    )

    def handle(self, *args, **options):
        def traverse_folder(folder):
            for dirpath, dirnames, filenames in walk(folder):
                for f in filenames:
                    MediaInfo(path.join(dirpath, f)).run()

        #TODO it may take a long time, so should add keyboard interrupt handler
        now = datetime.utcnow().replace(tzinfo=utc)
        for folder in settings.MEDIA_FOLDER:
            traverse_folder(folder)
        # remove old
        objs = MediaFile.objects.filter(utime__lte=now)
        objs.delete()


class MediaInfo(object):
    """ gather media info from command mediainfo and store to database
    """
    def __init__(self, filename):
        self._filename = filename

    def run(self):
        try:
            self.store(self.parse(self.execute()))
        except NotMediaFileException:
            logger.debug('skip: ' + self._filename)
        except MediaInfoNoVideoStreamException:
            logger.debug('skip: No video: ' + self._filename)
        except MediaInfoNoGeneralStreamException:
            logger.debug('skip: No general: ' + self._filename)

    def store(self, mediainfo_dict):
        try:
            # check exist
            objs = MediaFile.objects.filter(
                dirname=path.dirname(self._filename),
                basename=path.basename(self._filename))
            if len(objs) >= 1:
                objs.delete()
            # update record
            general = mediainfo_dict['general'][0]
            video = mediainfo_dict['video'][0]
            acodec = mediainfo_dict['audio'][0]['format'] \
                if len(mediainfo_dict['audio']) > 0 else ''
            width = height = duration = size = 0
            for field in general['duration'].split():
                if field.endswith('s'):
                    duration += int(field[:-1])
                elif field.endswith('mn'):
                    duration += int(field[:-2]) * 60
                elif field.endswith('h'):
                    duration += int(field[:-2]) * 60 * 60
            fstat = stat(self._filename)
            mtime = datetime.fromtimestamp(fstat.st_mtime, utc)
            size = fstat.st_size
            width = int(video['width'].split()[0])
            height = int(video['height'].split()[0])
            mf = MediaFile(dirname=path.dirname(self._filename),
                           basename=path.basename(self._filename),
                           size=size,
                           duration=duration,
                           width=width,
                           height=height,
                           format=general['format'],
                           acodec=acodec,
                           vcodec=video['format'],
                           mtime=mtime
                           )
            mf.save()
            logger.info('Add one media: ' + str(mf))
        except KeyError as e:
            logger.error('Write MediaFile: KeyError: {0}: {1}'.format(
                self._filename, e))
        except OSError as e:
            logger.error('Write MediaFile: OSError: {0}: {1}'.format(
                self._filename, e))
        except Exception as e:
            import sys
            import traceback
            traceback.print_tb(sys.exc_info()[2])
            logger.error('Write MediaFile: Exception: {0}: {1}'.format(
                self._filename, e))

    def parse(self, mediainfo_str):
        def state_content(line):
            fields = line.split(':')
            if len(fields) != 2:
                try:
                    result[self.title].append(self.content)
                except:
                    logger.error('Undefined mediainfo type: ' + self.title)
                self.content = {}
                return state_new
            self.content[fields[0].strip().lower()] = fields[1].strip()
            return state_content

        def state_new(line):
            func_map = {'General': state_content,
                        'Video': state_content,
                        'Audio': state_content,
                        }
            if line in func_map:
                self.title = line.lower()
                return func_map[line]
            return state_new

        result = {'general': [], 'audio': [], 'video': []}
        self.content = {}
        self.title = ''
        func = state_new
        for line in mediainfo_str.split('\n'):
            func = func(line.strip())
        if len(result['general']) <= 0:
            raise MediaInfoNoGeneralStreamException
        if len(result['video']) <= 0:
            raise MediaInfoNoVideoStreamException
        return result

    def execute(self):
        def is_one_of_postfix(str, postfixes):
            for postfix in postfixes:
                if str.endswith(postfix):
                    return True
            return False

        if not is_one_of_postfix(self._filename, settings.MEDIA_POSTFIX):
            raise NotMediaFileException()
        cmd = ShellCommand('mediainfo \'' + self._filename + '\'').run()
        if cmd.returncode != 0:
            logger.warning('shell: return [{0}]: mediainfo {1}'.format(
                cmd.returncode, self._filename))
            return
        return cmd.stdout


class ShellCommand(object):
    """Simple subprocess. Popen wrapper to run shell commands and log their
       output
    """
    def __init__(self, command_str, silent=False, verbose=False):
        self.command_str = command_str
        self.silent = silent
        self.verbose = verbose

        self.process = None
        self.stdout = None
        self.stderr = None
        self.time = None

    def run(self):
        """Execute shell command and return output and status
        """
        logger.debug('Executing: {0!r}...'.format(self.command_str))

        self.process = Popen(self.command_str,
                             shell=True,
                             stdout=PIPE,
                             stderr=PIPE)
        start = datetime.now()
        result = self.process.communicate()
        end = datetime.now()
        self.time = end - start

        self.returncode = self.process.returncode
        if self.returncode != 0 or not self.silent:
            stdout, stderr = result
            message = ['Output:'
                       '- returncode:\n{0}'.format(self.returncode)]
            if stdout:
                #if type(stdout) is bytes:
                #    stdout = stdout.decode()
                message.append('- stdout:\n{0}'.format(stdout))
            if stderr:
                if type(stderr) is bytes:
                    stderr = stderr.decode()
                message.append('- stderr:\n{0}'.format(stderr))
            if self.verbose:
                logger.debug('\n'.join(message))

            self.stdout = stdout
            self.stderr = stderr
        return self
