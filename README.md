
# Step1 : create google project 
- following : https://www.youtube.com/watch?v=6bzzpda63H0
- save client_secret in ./secret

# Step2 : create virtual env
- conda create --name youtube python=3.9
- conda activate youtube
- pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Step3 : verify if youtube account OK
- check with https://www.youtube.com/verify

# Step4 : Run codes
- run python GoogleService.py to give assess to project.
 
--> if error 400: redirect_uri_mismatch you can't sign in to this app because it doesn't comply with google's oauth 2.0 policy. if you're the app developer, register the redirect uri in the google cloud console.

# Step5 add authorized redirect URIs
go to https://console.cloud.google.com/apis/credentials/
add Authorized redirect URIs

# Step6:
- run main code with necessary modification for video file path

--> if get "googleapiclient.errors.HttpError: <HttpError 403 when requesting https://youtube.googleapis.com/upload/youtube/v3/videos?part=snippet%2Cstatus&alt=json&uploadType=multipart returned "YouTube Data API v3 has not been used in project 576480217806 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/youtube.googleapis.com/overview?project=576480217806 then retry."

--> just follow the instruction and will be OK
