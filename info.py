import os
from urllib.request import urlretrieve
from threading import Lock

class Item(object):
    def __init__(self):
        super().__init__()

        self.lock = Lock()
        self.id = None
        self.content = None
        self.post_time = 0
        self.comment_number = 0
        self.like_number = 0
        self.forward_number = 0
        self.device = None
        self.hyperlinks = set()
        self.pictures_url = set()

    def set_id(self, id):
        self.id = id

    def set_content(self, c):
        self.content = c

    def set_post_time(self, t):
        self.post_time = t

    def set_comment_number(self, n):
        self.comment_number = n

    def set_like_number(self, n):
        self.like_number = n

    def set_forward_number(self, n):
        self.forward_number = n

    def set_device(self, d):
        self.device = d

    def add_picture(self, url):
        with self.lock:
            self.pictures_url.add(url)

    def add_link(self, link):
        with self.lock:
            self.hyperlinks.add(link)

    def get_pictures_url(self):
        return self.pictures_url

    def to_string(self):
        r = '-' * 20 + '\n' + \
            "id: %s" % self.id + '\n' + \
            "%s" % self.content + "\n" + \
            "%s 来自 %s" % (self.post_time, self.device) + "\n" + \
            "转发[%d] 评论[%d] 赞[%d]" % (
                self.forward_number, self.comment_number, self.like_number)
        r += '\n' + str(self.hyperlinks or "no hyperlinks")
        r += '\n' + str(self.pictures_url or "no pictures")
        return r

    def download_pictures(self, path):
        for url in self.pictures_url:
            file_name = os.path.join(path, os.path.basename(url))
            urlretrieve(url, file_name)


class UserInfo(object):
    def __init__(self):
        super().__init__()

        self.nick_name = ""
        self.introduction = ""
        self.weibo_number = 0
        self.follow_number = 0
        self.fans_number = 0

    def get_nick_name(self):
        return self.nick_name

    def set_nick_name(self, n):
        self.nick_name = n

    def set_introduction(self, i):
        self.introduction = i

    def set_weibo_num(self, n):
        self.weibo_number = n

    def set_follow_num(self, n):
        self.follow_number = n

    def set_fans_num(self, n):
        self.fans_number = n

    def to_string(self):
        r = "昵称: %s" % self.nick_name + '\n' +\
            "简介: %s" % self.introduction + '\n' +\
            "微博: %d 关注: %d 粉丝: %d" % (
                self.weibo_number, self.follow_number, self.fans_number)
        return r
