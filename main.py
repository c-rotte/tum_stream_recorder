import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta

import requests


def main():
    # args: main.py <TUM id> <password> <catalog id> <lecture date (YYYY-mm-dd-HH-MM)>
    argv = sys.argv;
    # invalid amount of args
    if len(argv) != 5:
        printerror("Invalid amount of arguments");
        return

    tumid = argv[1]
    password = argv[2]
    catalogid = argv[3]
    # allow full catalog urls
    if "streams.tum.de" in catalogid:
        catalogid = catalogid.replace("https://streams.tum.de/Mediasite/Catalog/catalogs", "").replace("/", "")

    lecture_date = 0
    try:
        lecture_date = datetime.strptime(argv[4], "%Y-%m-%d-%H-%M")
    except ValueError:
        printerror("Invalid date")
        return

    print(
        "Using the following details: TUM-ID=" + tumid + "; password=" + password + "; catalog=https://streams.tum.de/Mediasite/Catalog/catalogs/"
        + catalogid + "; lectureStart=" + lecture_date.strftime("%Y-%m-%d %H:%M:%S"))
    print("Continue? (y/n)")
    userinput = input()
    # clear console because of the password
    clearconsole()
    if userinput != "y":
        return

    # waits(livestreams usually start some minutes earlier, hence 5 min)
    # waituntil(lecture_date, 5 * 60)

    # scrape links of newest livestream
    links = lookforlivestream(tumid, password, catalogid)

    # save to <randomnumber>.mp4
    recordStream(links, str(random.randint(100000000000, 999999999999)))


def printerror(error):
    print(error + "; Usage: main.py <TUM id> <password> <catalog id> <lecture date (YYYY-mm-dd-HH-MM)>");


def clearconsole():
    os.system('cls' if os.name == 'nt' else 'clear')


def lookforlivestream(tumid, password, catalogid):
    print("Scraping links...")

    # keeping the session helps saving cookies
    session = requests.Session()

    # login url with return url
    url = "https://streams.tum.de/Mediasite/Login/?ReturnUrl=" + requests.utils.quote(
        "/Mediasite/Catalog/catalogs/" + catalogid, safe='')
    # get login page (redirecting)
    session.get("https://streams.tum.de/Mediasite/Catalog/catalogs/" + catalogid, headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Host": "streams.tum.de"
        })

    # logging in
    session.post(url,
                 data={
                     "UserName": tumid, "Password": password, "RememberMe": "true",
                     "RememberMe": "false"
                     },
                 headers={
                     "Host": "streams.tum.de",
                     "Origin": "https://streams.tum.de",
                     "Referer": url
                     })

    # getting catalog
    presentationresponse = session.post("https://streams.tum.de/Mediasite/Catalog/Data/GetPresentationsForFolder",
                                        data={
                                            "IsViewPage": "true",
                                            "IsNewFolder": "true",
                                            "CatalogId": catalogid, "CurrentFolderId": catalogid,
                                            "ItemsPerPage": "50",
                                            "PageIndex": "0",
                                            "PermissionMask": "Execute",
                                            "CatalogSearchType": "SearchInFolder",
                                            "SortBy": "Date",
                                            "SortDirection": "Descending",
                                            "Url": "https://streams.tum.de/Mediasite/Catalog/catalogs/" + catalogid
                                            },
                                        headers={
                                            "Host": "streams.tum.de",
                                            "Origin": "https://streams.tum.de",
                                            "Referer": "https://streams.tum.de/Mediasite/Catalog/catalogs/" + catalogid
                                            })

    if presentationresponse.status_code != 200:
        print("Couldn't get the catalog. " + presentationresponse.status_code)
        return

    jsonresponse = presentationresponse.json()
    detailslist = jsonresponse["PresentationDetailsList"]

    livestreamurl = 0
    livestreamid = 0

    # finding livestreams (NOT YET TESTED!)
    for presentationdetail in detailslist:
        if (presentationdetail["StatusDisplay"] == "Live"):
            livestreamurl = presentationdetail["PlayerUrl"]
            livestreamid = presentationdetail["Id"]
            print("Found livestream: \"" + presentationdetail["Name"] + "\" (" + presentationdetail[
                "AirDateDisplay"] + ")")
        break

    if livestreamurl == 0:
        print("Sorry, it looks like there's no livestream at the moment.")
        return

    # second url
    url = "https://streams.tum.de/Mediasite/Login/?ReturnUrl=" + requests.utils.quote(
        "/Mediasite/Play/" + livestreamid + "?catalog=" + catalogid, safe='')
    # getting the actual m3u8 source
    playeroptionsresponse = session.post(
        "https://streams.tum.de/Mediasite/PlayerService/PlayerService.svc/json/GetPlayerOptions",
        headers={
            "Host": "streams.tum.de",
            "Origin": "https://streams.tum.de",
            "Referer": "https://streams.tum.de/Mediasite/Play/" + livestreamid + "?catalog=" + catalogid,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
            },
        json={
            "getPlayerOptionsRequest": {
                "ResourceId": livestreamid,
                "QueryString": "?catalog=" + catalogid,
                "UseScreenReader": "false",
                "UrlReferrer": url,
                "X-Requested-With": "XMLHttpRequest"
                }
            })

    playerjson = playeroptionsresponse.json()["d"]
    presentation = playerjson["Presentation"]["Streams"][0]["VideoUrls"][0]["Location"]
    presentation = presentation.replace("manifest?playbackTicket", "manifest(format=m3u8-aapl).m3u8?playbackTicket")
    cam = playerjson["Presentation"]["Streams"][1]["VideoUrls"][0]["Location"]
    cam = cam.replace("manifest?playbackTicket", "manifest(format=m3u8-aapl).m3u8?playbackTicket")

    print("Got the presentation: " + presentation)
    print("Got the cam: " + cam)

    return [presentation, cam]


def recordStream(links, name):
    presentation = links[0]
    cam = links[1]

    print("Recording...")

    # merging the two video streams and saving them in a .mp4
    ffmpegprocess = subprocess.Popen(["ffmpeg",
                                      "-re",
                                      "-hide_banner",
                                      "-y",
                                      "-i",
                                      presentation,
                                      "-i",
                                      cam,
                                      "-preset",
                                      "ultrafast",
                                      "-movflags",
                                      "+faststart",
                                      "-c:v",
                                      "libx264",
                                      "-c:a",
                                      "aac",
                                      "-t",
                                      "03:00:00",
                                      "-crf",
                                      "18",
                                      "-filter_complex",
                                      # merging
                                      "[1:v][0:v]scale2ref=main_w:ih[sec][pri]; [sec]setsar=1,drawbox=c=black:t=fill[sec];[pri][sec]hstack[canvas]; [canvas][1:v]overlay=main_w-overlay_w,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1",
                                      name + ".mp4"], cwd=os.path.dirname(os.path.realpath(__file__)))

    out, err = ffmpegprocess.communicate()
    errcode = ffmpegprocess.returncode


def waituntil(date, less):
    date -= timedelta(seconds=less)
    diff = date.timestamp() - datetime.now().timestamp()
    if diff <= 0:
        return
    print("Waiting ", int(diff), "s... until " + date.strftime("%Y-%m-%d %H:%M:%S"))
    time.sleep(diff)


main()
