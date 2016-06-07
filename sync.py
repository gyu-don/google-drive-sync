import requests
import json
from pprint import pprint
from collections import deque
import datetime
import copy
import os
import fnmatch
import http.server
import webbrowser
import easycrypt

SYNC_PATH = "googledrive"

IGNORELIST_PATH = "ignore.txt"
IGNORELIST_ENCODING = "utf-8"

class GoogleApiError(Exception):
    pass

class GoogleDriveApi:
    API_FILE = "api.bin"
    TOKEN_FILE = "token.bin"
    SCOPE_ADDR = "https://www.googleapis.com/auth/drive.readonly"
    API_ADDR = "https://www.googleapis.com/drive/v3/files"

    def _initial_auth(self):
        with open(self.API_FILE, "rb") as f:
            api = json.loads(easycrypt.decrypt(f.read(), "b0de"+"4bcb1"+"b577c5e"))["installed"]
        r = requests.get(api["auth_uri"], params={
                "response_type": "code",
                "scope": self.SCOPE_ADDR,
                "redirect_uri": "http://localhost:8000",
                "client_id": api["client_id"]})
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"Accepted. Please close this.\r\n"
                self.server.mydata = self.path[self.path.find("code=")+5:]
                self.send_response(202)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.send_header("Content-length", len(body))
                self.end_headers()
                self.wfile.write(body)

        print("Please Allow this program accessing to Google Drive.")
        webbrowser.open(r.url)
        httpd = http.server.HTTPServer(("", 8000), Handler)
        httpd.handle_request()
        httpd.server_close()
        code = httpd.mydata
        r = requests.post(api["token_uri"], data={
                "code": code,
                "client_id": api["client_id"],
                "client_secret": api["client_secret"],
                "redirect_uri": "http://localhost:8000",
                "grant_type": "authorization_code"})
        token = json.loads(r.text)
        if "error" in token:
            raise GoogleApiError(token["error"])
        with open(self.TOKEN_FILE, "wb") as f:
            f.write(easycrypt.encrypt(json.dumps(token), "b0de4b"+"cb1b577"+"c5e"))
        self.api = api
        self.token = token

    def auth(self):
        try:
            with open(self.TOKEN_FILE, "rb") as f:
                token = json.loads(easycrypt.decrypt(f.read(), "b0de"+"4bcb1"+"b577c5e"))
                self.token = token
        except FileNotFoundError:
            token = self._initial_auth()

    def driveRequest(self, param, drive_id=None, _refresh_when_failed=True):
        param = copy.copy(param)
        param["access_token"] = self.token["access_token"]
        if drive_id is None:
            addr = self.API_ADDR
        else:
            addr = self.API_ADDR + "/" + drive_id
        r = requests.get(addr, param)
        if r.status_code != 200:
            res = json.loads(r.text)
            if _refresh_when_failed:
                self._refresh_token()
                self.driveRequest(param, _refresh_when_failed=False)
            else:
                raise GoogleApiError(r.url, res["error"])
        return r

    def _refresh_token(self):
        try:
            self.api
        except AttributeError:
            with open(self.API_FILE) as f:
                self.api = json.load(f)["installed"]
        r = requests.post(self.api["token_uri"], data={
                "client_id": self.api["client_id"],
                "client_secret": self.api["client_secret"],
                "refresh_token": self.token["refresh_token"],
                "grant_type": "refresh_token"})
        newtoken = json.loads(r.text)
        for k in newtoken:
            self.token[k] = newtoken[k]
        with open(self.TOKEN_FILE, "w") as f:
            json.dump(self.token, f)

def sync(api, ignorelist):
    queue = deque([("", "root")])
    while len(queue):
        localpath, driveid = queue.popleft()
        print(localpath)
        if not os.path.exists(os.path.join(SYNC_PATH, localpath)):
            os.mkdir(os.path.join(SYNC_PATH, localpath))
        nextPageToken = None
        while 1:
            param = {"q": "'{}' in parents and trashed = false".format(driveid),
                     "fields": "files(id,mimeType,modifiedTime,name),nextPageToken"}
            if nextPageToken:
                param["pageToken"] = nextPageToken
            res = json.loads(api.driveRequest(param).text)
            nextPageToken = res.get("nextPageToken", None)
            for f in res["files"]:
                localname = os.path.join(localpath, f["name"])
                localfull = os.path.join(SYNC_PATH, localname)
                if any(fnmatch.fnmatch(localname, ign) for ign in ignorelist):
                    print(localname + "\t-- Ignored.")
                    continue
                elif f["mimeType"] == "application/vnd.google-apps.folder":
                    queue.append((localname, f["id"]))
                else:
                    if "application/vnd.google-apps" in f["mimeType"]:
                        print(localname + "\t-- Google Docs. Not Downloaded.")
                        continue
                    elif os.path.exists(localfull):
                        ldt = datetime.datetime.utcfromtimestamp(os.stat(localfull).st_mtime)
                        gdt = datetime.datetime.strptime(f["modifiedTime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                        if ldt >= gdt:
                            print(localname + "\t-- Not modified")
                            continue
                    download = api.driveRequest({"alt": "media"}, f["id"])
                    with open(localfull, "wb") as out:
                        out.write(download.content)
                    print(localname + "\t-- Downloaded")
            if nextPageToken is None:
                break

if __name__ == "__main__":
    ignorelist = []
    try:
        with open(IGNORELIST_PATH, encoding=IGNORELIST_ENCODING) as f:
            for line in f:
                ignorelist.append(line.rstrip("\n"))
    except IOError:
        pass
    api = GoogleDriveApi()
    api.auth()
    sync(api, ignorelist)
