from django.db import models


class MediaFile(models.Model):
    dirname = models.CharField(max_length=512)
    basename = models.CharField(max_length=512)
    size = models.IntegerField()
    duration = models.IntegerField()
    width = models.IntegerField()
    height = models.IntegerField()
    format = models.CharField(max_length=32)
    acodec = models.CharField(max_length=32)
    vcodec = models.CharField(max_length=32)
    mtime = models.DateTimeField()
    utime = models.DateTimeField(auto_now=True, auto_now_add=True)

    class Meta:
        unique_together = ("dirname", "basename")
        ordering = ['-mtime', 'dirname', 'basename']

    def __str__(self):
        h = self.duration / 60 / 60
        m = self.duration / 60 % 60
        s = self.duration % 60
        return "{0}: [{1} KB][{2}:{3}:{4}][{5}x{6}][{7}][{8}][{9}]".format(
            self.basename,
            self.size / 1000,
            h, m, s,
            self.width, self.height,
            self.format, self.vcodec, self.acodec
        )
