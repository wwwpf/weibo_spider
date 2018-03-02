import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from random import uniform

import requests
from bs4 import BeautifulSoup

from info import Item, UserInfo
from utils import create_dir


def parse_post_time(publish_time):
    if "刚刚" in publish_time:
        publish_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    elif "分钟" in publish_time:
        minute = publish_time[:publish_time.find("分钟")]
        minute = timedelta(minutes=int(minute))
        publish_time = (
            datetime.now() - minute).strftime(
            "%Y-%m-%d %H:%M")
    elif "今天" in publish_time:
        today = datetime.now().strftime("%Y-%m-%d")
        time = publish_time[3:]
        publish_time = today + " " + time
    elif "月" in publish_time:
        year = datetime.now().strftime("%Y")
        month = publish_time[0:2]
        day = publish_time[3:5]
        time = publish_time[7:12]
        publish_time = (
            year + "-" + month + "-" + day + " " + time)
    else:
        publish_time = publish_time[:19]

    return publish_time


class WeiBoSpider:

    host = "https://weibo.cn"

    def __init__(self, cookies, fetch_id, fetch_pic=False):

        self.fetch_id = fetch_id
        self.fetch_pic = fetch_pic

        self.user_url = "https://weibo.cn/u/%d?filter=1"
        self.cookies = {"Cookie": cookies}
        self.session = requests.Session()

        self.user_info = UserInfo()

        self.pool = ThreadPoolExecutor(max_workers=50)
        self.futures = []

        self.item_list = []

    def start(self):
        try:
            response = self.session.get(self.user_url %
                                        self.fetch_id, cookies=self.cookies)
            if not self.check_response(response):
                return

            response.encoding = "utf-8"

            self.bs_obj = BeautifulSoup(response.text, "html.parser")

            self.get_user_information()

            # 第一页
            self.current_page = 1
            self.process_page()

            page_number = 1
            page_label = self.bs_obj.find("input", {"name": "mp"})
            if page_label:
                page_number = int(page_label["value"])
            # 后续页
            for p in range(2, page_number + 1):
                current_page_url = "https://weibo.cn/u/%d?filter=1&page=%d" % (
                    self.fetch_id, p)

                response = self.session.get(
                    current_page_url, cookies=self.cookies)
                if not self.check_response(response):
                    continue

                response.encoding = "utf-8"
                self.bs_obj = BeautifulSoup(response.text, "html.parser")
                self.process_page()

            wait(self.futures, 10)

        except Exception as e:
            print(e)
            self._handle_exception()

    def process_page(self):
        '''处理每一页'''

        if not self.bs_obj:
            return
        try:
            print("start process page:", self.current_page)
            weibos = self.bs_obj.find_all("div", {"class": "c"}, id=True)

            for weibo in weibos:
                item = Item()
                weibo_id = weibo["id"]
                print("process id", weibo_id)
                item.set_id(weibo_id)

                has_full_content = False

                # https://weibo.cn/comment/%s 不显示设备来源
                # 时间及设备
                time_label = weibo.find("span", {"class": "ct"})
                if time_label:
                    s = time_label.get_text()

                    from_index = s.find("来自")
                    publish_time = s[:from_index]
                    publish_time = parse_post_time(publish_time)

                    device = s[from_index + 2:]

                    item.set_post_time(publish_time)
                    item.set_device(device)

                # 正文
                content_label = weibo.find("span", {"class": "ctt"})
                if content_label:

                    full_content = content_label.find(
                        "a", {"href": "/comment/%s" % weibo_id[2:]})
                    # 未显示全文
                    if full_content:
                        weibo_url = self._add_url_prefix(full_content["href"])
                        retry = 2
                        continue_flag = False
                        while retry > 0:
                            new_rsp = self.session.get(
                                weibo_url, cookies=self.cookies)
                            if not self.check_response(new_rsp):
                                continue_flag = True
                                break

                            new_rsp.encoding = "utf-8"
                            new_bs_obj = BeautifulSoup(
                                new_rsp.text, "html.parser")
                            weibo = new_bs_obj.find(
                                "div", {"class": "c"}, id=True)
                            if weibo:
                                break
                            retry -= 1
                        if continue_flag or retry == 0:
                            continue

                        content_label = weibo.find("span", {"class": "ctt"})
                        has_full_content = True

                    # 处理换行符
                    for br in content_label.find_all("br"):
                        br.replace_with('\n')

                    try:
                        if has_full_content:
                            content = content_label.text[1:]
                        else:
                            content = content_label.text[:-4]
                        item.set_content(content)
                    except Exception as e:
                        print(e)

                    self.parse_hyperlinks(item, content_label)

                datas = weibo.find_all("a")
                has_pictures = False
                for data in datas:
                    url = data["href"]

                    # 转评赞数据
                    s = data.text
                    begin = s.find('[')
                    end = s.rfind(']')
                    num = 0
                    try:
                        if begin >= 0 and end >= 0:
                            num = int(s[begin + 1:end])
                    except Exception as e:
                        pass

                    # 转发
                    if "weibo.cn/repost" in url:
                        item.set_forward_number(num)
                    # 评论
                    elif "weibo.cn/comment" in url:
                        item.set_comment_number(num)
                    # 赞
                    elif "weibo.cn/attitude" in url:
                        item.set_like_number(num)
                    # 组图
                    elif self.fetch_pic and "/mblog/picAll/" in url:
                        self.futures.append(self.pool.submit(
                            self.parse_pictures, item, url))
                        # self.parse_pictures(item, url)
                        has_pictures = True

                # 单张图片
                if self.fetch_pic and not has_pictures:
                    img_label = weibo.find("img", src=True)
                    if img_label:
                        temp_url = img_label["src"]
                        prefix = temp_url[:temp_url.find(".cn") + 3]
                        base_name = os.path.basename(temp_url)
                        pic_url = prefix + "/large/" + base_name
                        item.add_picture(pic_url)

                self.item_list.append(item)

            print("page %d done" % self.current_page)

            # 加入 sleep 仍然 403
            # wait_seconds = uniform(0, 1)
            # if self.current_page % 10 == 0:
            #     wait_seconds = uniform(17, 31)
            # print("wait for %.2fs" % wait_seconds)
            # time.sleep(wait_seconds)

            self.current_page += 1
        except Exception as e:
            self._handle_exception()

    def save(self):
        if not self.item_list:
            print("no data")
            return

        print("write to file")
        try:
            nick_name = self.user_info.get_nick_name()

            # 创建文件夹
            create_dir(nick_name)

            weibo_file = os.path.join(nick_name, "weibo.txt")
            with open(weibo_file, "w", encoding="utf-8") as f:
                f.write(self.user_info.to_string())
                f.write("\n\n\n")
                for item in self.item_list:
                    f.write(item.to_string())
                    f.write("\n")

            if self.fetch_pic:
                picture_url_file = os.path.join(nick_name, "pictures.txt")
                with open(picture_url_file, "w", encoding="utf-8") as f:
                    for item in self.item_list:
                        for url in item.get_pictures_url():
                            f.write(url)
                            f.write("\n")

            print("write done")
        except Exception as e:
            print(e)
            with open("error%d.txt" % int(time.time()), "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)

    def check_response(self, rsp):
        if not rsp.ok:
            print("error code:", rsp.status_code)
            return False
        return True

    def get_user_information(self):
        if not self.bs_obj:
            return

        try:
            # 昵称
            title_label = self.bs_obj.find("title")
            if not title_label:
                return
            title = title_label.text
            self.user_info.set_nick_name(title[:-3])

            # 简介
            introduction_label = self.bs_obj.find(
                "span", {"style": "word-break:break-all; width:50px;"})
            if introduction_label:
                self.user_info.set_introduction(introduction_label.text)

            # 微博数
            weibo_num_label = self.bs_obj.find("span", {"class": "tc"})
            if weibo_num_label:
                self.user_info.set_weibo_num(
                    int(re.findall(r"\d+", weibo_num_label.text)[0]))

            # 关注数
            follow_num_label = self.bs_obj.find(
                "a", {"href": "/%d/follow" % self.fetch_id})
            if follow_num_label:
                self.user_info.set_follow_num(int(re.findall(
                    r"\d+", follow_num_label.text)[0]))

            # 粉丝数
            fans_num_label = self.bs_obj.find(
                "a", {"href": "/%d/fans" % self.fetch_id})
            if fans_num_label:
                self.user_info.set_fans_num(
                    int(re.findall(r"\d+", fans_num_label.text)[0]))
        except Exception as e:
            print(e)
            self._handle_exception()

    def parse_pictures(self, item, url):
        '''处理组图'''

        url = self._add_url_prefix(url)

        rsp = self.session.get(url, cookies=self.cookies)
        if not self.check_response(rsp):
            return

        bs_obj = BeautifulSoup(rsp.text, "html.parser")
        pictures = bs_obj.find_all("img", src=True)
        for p in pictures:
            temp_url = p["src"]
            base_name = os.path.basename(temp_url)
            prefix = temp_url[:temp_url.find(".cn") + 3]
            first_w = prefix.find("w")
            prefix = prefix[:first_w + 1] + "x" + prefix[first_w + 2:]
            pic_url = prefix + "/large/" + base_name
            item.add_picture(pic_url)

    def parse_hyperlinks(self, item, content):
        '''获取正文中的超链接'''

        hrefs = content.find_all("a")
        for h in hrefs:
            url = h["href"]
            url = self._add_url_prefix(url)
            item.add_link((h.text, url))

    def _handle_exception(self):
        with open("error%d.txt" % int(time.time()), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        self.save()

    def _add_url_prefix(self, url):
        if url[0] != 'h':
            url = self.host + url
        return url


def main():
    cookies = "自己的 cookie"
    fetch_id = 1669879400  # 需要抓取的微博id
    fetch_pic = False

    weibo = WeiBoSpider(cookies, fetch_id, fetch_pic)
    weibo.start()
    weibo.save()


if __name__ == "__main__":
    main()
