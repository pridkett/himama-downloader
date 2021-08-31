#!/usr/bin/python
"""
A simple program to download all the images from HiMama

With my offspring leaving daycare soon, I wanted to create a simple program to
go through and download all of the images that daycare had taken of her. This
program uses the HiMama JSON API to download all of the images and, hopefully,
preserve all of the metadata. Yay!
"""

from optparse import OptionParser
import datetime
import configparser
import json
import sys
import pathlib
import requests
import piexif
import math
import os
import subprocess

from http.cookiejar import MozillaCookieJar
from typing import Dict, Any, Tuple, Iterable, Optional, BinaryIO, List

BASE_URL = "https://www.himama.com/accounts/{account}/journal_api?page={page}"


def update_image_metadata(
    image_path: pathlib.Path,
    created_at: datetime.datetime = None,
    title: str = None,
    description: str = None,
    gps: Tuple[float, float] = None,
    keywords: Iterable[str] = None,
):
    """Set the exif metadata for the images"""

    exif_dict = piexif.load(str(image_path))
    if created_at is not None:
        formatted_timestamp = created_at.astimezone().strftime("%Y:%m:%d %H:%M:%S")
        formatted_tz = created_at.astimezone().strftime("%z")
        formatted_tz = formatted_tz[:-2] + ":" + formatted_tz[-2:]
        exif_dict["1st"][piexif.ImageIFD.DateTime] = formatted_timestamp
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = formatted_timestamp
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = formatted_timestamp

        exif_dict["Exif"][piexif.ExifIFD.OffsetTime] = formatted_tz
        exif_dict["Exif"][piexif.ExifIFD.OffsetTimeOriginal] = formatted_tz
        exif_dict["Exif"][piexif.ExifIFD.OffsetTimeDigitized] = formatted_tz

    exif_desc = None
    if title:
        if description:
            exif_desc = title + " - " + description
        else:
            exif_desc = title
    elif description:
        exif_desc = description

    if exif_desc is not None:
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = exif_desc
    print(exif_desc)
    exif_bytes = piexif.dump(exif_dict)
    piexif.insert(exif_bytes, str(image_path))

    # shell out to exiftool to do a lot more work
    # see: https://akrabat.com/setting-title-and-caption-with-exiftool/
    args = []  # type: List[str]
    if keywords:
        keyword_args = ", ".join(keywords)
        args.append(f'-xmp:Subject="{keyword_args}"')
        args.append(f'-iptc:Keywords="{keyword_args}"')
    if title:
        cmdline_title = title.replace('"', "'")
        cmdline_title = "".join([c for c in cmdline_title if 32 <= ord(c) <= 127])
        args.append(f'-iptc:ObjectName="{cmdline_title}"')
        args.append(f'-xmp:Title="{cmdline_title}"')
    if description:
        cmdline_description = description.replace('"', "'")
        cmdline_description = "".join(
            [c for c in cmdline_description if 32 <= ord(c) <= 127]
        )
        args.append(f'-iptc:Caption-Abstract="{cmdline_description}"')
        args.append(f'-xmp:Description="{cmdline_description}"')

    if gps is not None:
        latitude_ref = "N" if gps[0] > 0 else "S"
        longitude_ref = "E" if gps[1] > 0 else "W"
        args.append(f"-GPSLatitude={abs(gps[0])}")
        args.append(f"-GPSLatitudeRef={latitude_ref}")
        args.append(f"-GPSLongitude={abs(gps[1])}")
        args.append(f"-GPSLongitudeRef={longitude_ref}")

    if args:
        args.append(str(image_path))
        args.insert(0, "exiftool")
        success = subprocess.run(args)
        print(success)

    # set the filesystem time to match when the photo was created
    if created_at:
        os.utime(image_path, (created_at.timestamp(), created_at.timestamp()))


def process_activity(
    activity: Dict[str, Any],
    output_path: pathlib.Path,
    gps: Tuple[float, float] = None,
    keywords: Optional[Iterable[str]] = None,
):
    print(json.dumps(activity, indent=2))
    json_file = output_path / "{}.json".format(activity["id"])  # type: pathlib.Path
    if json_file.exists():
        return
    with json_file.open(mode="w") as f:
        f.write(json.dumps(activity, indent=2))

    ok = False

    # download the images too
    if "image" in activity and "url" in activity["image"] and activity["image"]["url"]:
        image_path = output_path / "{}.jpg".format(activity["id"])  # type: pathlib.Path
        r = requests.get(activity["image"]["url"], stream=True)
        if r.status_code == 200:
            with image_path.open("wb") as image_file:  # type: BinaryIO
                for chunk in r.iter_content(1024):
                    image_file.write(chunk)
        ok = True

        update_image_metadata(
            image_path,
            created_at=datetime.datetime.fromisoformat(activity["created_at"]),
            title=activity["title"],
            description=activity["description"],
            gps=gps,
            keywords=keywords,
        )

    # download the videos too
    if "video" in activity and "url" in activity["video"] and activity["video"]["url"]:
        video_path = output_path / "{}.mp4".format(activity["id"])  # type: pathlib.Path
        r = requests.get(activity["video"]["url"], stream=True)
        if r.status_code == 200:
            with video_path.open("wb") as video_file:  # type: BinaryIO
                for chunk in r.iter_content(1024):
                    video_file.write(chunk)
        raise Exception(f"video status code: {r.status_code}")
        ok = True
        # TODO: Augment metadata

    if not (ok):
        raise Exception("activity: %d - no image or video???" % (activity["id"]))


def process_page(
    content: Dict[str, Any],
    output_path: pathlib.Path,
    gps: Tuple[float, float] = None,
    keywords: Optional[Iterable[str]] = None,
):
    for _, val in content["intervals"].items():
        for activity in val:
            process_activity(activity["activity"], output_path, gps, keywords)


def main(
    account: str,
    cookie_file: str,
    output_path: pathlib.Path,
    gps: Tuple[float, float] = None,
    keywords: Optional[Iterable[str]] = None,
):

    # if the output directory doesn't exist, create it
    if not output_path.exists():
        output_path.mkdir(parents=True)

    cj = MozillaCookieJar(filename=cookie_file)
    cj.load()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:91.0) Gecko/20100101 Firefox/91.0",
        "DNT": "1",  # look more like a real request
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Host": "www.himama.com",
        "If-None-Match": 'W/"86d238f2d6ebca4fa068d4ad39e76a99"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-GPC": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    page = 1
    while True:
        target_url = BASE_URL.format(account=account, page=page)
        r = requests.get(target_url, headers=headers, cookies=cj)
        # print(json.dumps(dict(r.request.headers), indent=2))
        # print(json.dumps(dict(r.headers), indent=2))
        # print(target_url)
        # print(r.status_code)
        # print(json.dumps(r.json(), indent=2))

        page_data = r.json()
        if "intervals" in page_data and page_data["intervals"]:
            process_page(r.json(), output_path, gps, keywords)
        else:
            print(f"Appears complete on page {page}")
            break

        page = page + 1


if __name__ == "__main__":
    parser = OptionParser(usage="usage: %prog [options] filename", version="%prog 1.0")

    parser.add_option(
        "-i",
        "--ini",
        action="store",
        dest="inifile",
        default=None,
        help="INI file to use for configuration",
    )

    parser.add_option(
        "-a",
        "--account",
        action="store",
        dest="account",
        default=None,
        help="HiMama Account ID",
    )

    parser.add_option(
        "-c",
        "--cookie",
        action="store",
        dest="cookiefile",
        default=None,
        help="cookiejar file extracted from web interface",
    )

    parser.add_option(
        "-o",
        "--output",
        action="store",
        dest="outputdir",
        default=None,
        help="directory to save output into",
    )

    (options, args) = parser.parse_args()

    cookie_file = None
    account = None
    output_path = None
    keywords = []
    gps = None
    if options.inifile:
        config = configparser.ConfigParser()
        config.read(options.inifile)

        if "CookieFile" in config["DEFAULT"]:
            cookie_file = config["DEFAULT"]["CookieFile"]
        if "Account" in config["DEFAULT"]:
            account = config["DEFAULT"]["Account"]
        if "OutputDir" in config["DEFAULT"]:
            output_path = pathlib.Path(config["DEFAULT"]["outputdir"])
        if "lat" in config["DEFAULT"] and "lon" in config["DEFAULT"]:
            gps = (float(config["DEFAULT"]["lat"]), float(config["DEFAULT"]["lon"]))
        if "keywords" in config["DEFAULT"]:
            keywords = [x.strip() for x in config["DEFAULT"]["keywords"].split(",")]

    if options.account:
        account = options.account

    if options.cookiefile:
        cookie_file = options.cookiefile

    if options.outputdir:
        output_path = pathlib.Path(options.outputdir)

    if not account or not cookie_file:
        print("must specify both account and cookiefile")
        sys.exit(1)

    main(
        account=account,
        cookie_file=cookie_file,
        output_path=output_path,
        gps=gps,
        keywords=keywords,
    )
