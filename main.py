from typing import List
from pathlib import Path
from GoogleService import Create_Service
from googleapiclient.http import MediaFileUpload

class YoutubeUploader:
    """this class upload video to your youtube channel (with a single file or a full folder)

    Returns:
        [None]: [this class doesn't return anything]
    """

    CLIENT_SECRET_FILE = r'./secret/secret.json' # this is the file for connect to your project/youtube channel
    API_NAME = 'youtube' # no need to change
    API_VERSION = 'v3' # no need to change
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload'] # no need to change
    MAX_UPLOAD_NUM :int = int(10_000 / 1_600) #* this limitation comes from google api quota
    UPLOADED_FILES_TXT = Path(r"./uploaded_files.txt") # this is the file we used to keep track the videos we already uploaded
    TAGS = ['PLO']

    def __init__(self) -> None:
        """init function
        """
        self.service = Create_Service(self.CLIENT_SECRET_FILE, self.API_NAME,self.API_VERSION,self.SCOPES)

    def get_request_body(self,title:str) -> dict :
        """prepare request body to uploading

        Args:
            title (str): [title of your video]

        Returns:
            dict: [request body]
        """
        return {
            'snippet': {
                'title': title,
                'description': title,
                'tags': self.TAGS,
            },
            'status': {
                'privacyStatus': 'private',
                'selfDeclaredMadeForKids': False, 
            },
            'notifySubscribers': False
        }

    def upload_video(self, video_file_path:Path, request_body:dict) -> None:
        """upload video with request body

        Args:
            video_file_path (Path): [video file path]
            request_body (dict): [request body needed for upload, can be got from function <get_request_body>]
        """
        mediaFile = MediaFileUpload(video_file_path)
        response_upload = self.service.videos().insert(
            part='snippet,status',
            body=request_body,
            media_body=mediaFile
        ).execute()
        self.add_info_to_txt(info=str(video_file_path)) #this is used to key track of videos uploaded

    def add_info_to_txt(self, info:str) -> None:
        """add information to a txt file, txt file path is defined in class level

        Args:
            info (str): [information we want to add to txt]
        """
        with self.UPLOADED_FILES_TXT.open(mode='a') as f:
            f.write(info)
            f.write('\n')

    def get_file_list_from_txt(self) -> List[str]:
        """get file list from txt (uploaded videos list)

        Returns:
            [type]: [description]
        """
        if not self.UPLOADED_FILES_TXT.exists():
            return []
        else:
            with self.UPLOADED_FILES_TXT.open(mode='r') as f:
                path_str_list = f.readlines()
                path_list = [Path(x.strip('\n')) for x in path_str_list]
                return [str(x) for x in path_list]

    def upload_videos_from_folder(self, video_folder_path:Path, video_ext:str = '.mp4') -> None:
        """upload video from a folder path, this will try to upload whole folder videos, but limited numbers according to google api quota

        Args:
            video_folder_path (Path): [video folder path]
            video_ext (str, optional): [video extention]. Defaults to '.mp4'.
        """
        files = list(video_folder_path.glob(f"**/*{video_ext}"))
        count = 0
        for file in files:
            if str(file) not in self.get_file_list_from_txt(): # check if already uploaded
                title = file.stem
                request_body = self.get_request_body(title)
                print(f'uploding video :{title}{video_ext}')
                self.upload_video(file, request_body)
                count += 1

                if count == self.MAX_UPLOAD_NUM:
                    print(f'uploading for {self.MAX_UPLOAD_NUM} done ! This is the max number allowed')
                    break

if __name__ == '__main__':

    import socket
    socket.setdefaulttimeout(30000)
    plo_video_folder = Path(r'D:\01_Poker\88_PLO\Ups PLO Adv\2. Preflop')
    yt = YoutubeUploader()
    yt.upload_videos_from_folder(plo_video_folder, video_ext=".mp4")