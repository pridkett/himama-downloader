HiMama Downloader
=================

Patrick Wagstrom &lt;patrick@wagstrom.net&gt;<br>
August 2021

Overview
--------

This is a very simple project that was created to download all of your child's photos from HiMama. Make sure to run this before your child leaves the center or you may not be able to recover the files.

Dependencies
------------

It appears that the fine art of inserting metadata into photos is a complete mess if you want to EXIF, IPTC, XMP, and more. There are decent EXIF libraries for Python, but trying to do enough metadata to make it show up in Apple Photos is almost impossible. Therefore, most metadata is inserted using `exiftool`. You'll need to have it installed on your system for this to work.

Configuration
-------------

The easiest way is probably to create a `himama.ini`:

```ini
[DEFAULT]
Account = 123456
CookieFile = cookies.txt
OutputDir = output
lat = 32.22682 # latitude of childcare center
lon = -95.2255 # longitude of childcare center
keywords = Daycare, Your Center Name, Your Child Name
```

In addition, options can be passed through on the command line, use `python himama.py --help` for more information on the settings.

### Cookie Issues

I use the [Firefox Cookies.txt extension](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) to export the cookies from the Firefox web interface. Unfortunately, there is a very longstanding bug in Python that interprets cookies that are HTTP Only as comments.

```
#HttpOnly_www.himama.com	FALSE	/	TRUE	0	_himama_session	BLAH_SOME_REALLY_LONG_STRING
```

To fix this remove the string `#HttpOnly_` from the beginning of the line. You'll also need to change the `0` into the expiration from another cookie.

License
-------

Copyright (c) 2021 Patrick Wagstrom

Licensed under terms of the MIT License