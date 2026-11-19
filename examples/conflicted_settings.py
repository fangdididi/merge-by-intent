<<<<<<< HEAD
import os
import re
||||||| merged common ancestor
import os
=======
import os
import json
>>>>>>> feature/config-file

<<<<<<< HEAD
UPLOAD_TIMEOUT_S = 30  # slow NAS disks time out at 20
||||||| merged common ancestor
UPLOAD_TIMEOUT_S = 20
=======
UPLOAD_TIMEOUT_S = int(os.environ.get("UPLOAD_TIMEOUT_S", "20"))
>>>>>>> feature/config-file

<<<<<<< HEAD
def retries():
    return 3
||||||| merged common ancestor
def retries():
    return 3
=======
def retries():
    return int(os.environ.get("RETRIES", "3"))
>>>>>>> feature/config-file
