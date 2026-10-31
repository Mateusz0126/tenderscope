
import os

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

account = os.environ["sttenderscope123123"]

service = DataLakeServiceClient(
    account_url=f"https://{account}.dfs.core.windows.net",
    credential=DefaultAzureCredential(),
)

bronze = service.get_file_system_client("bronze")

file = bronze.get_file_client("sdk_smoke_test.txt")
file.upload_data(b"TenderScope Azure SDK works!", overwrite=True)

content = file.download_file().readall()
assert content == b"TenderScope Azure SDK works!"

file.delete_file()

print("ADLS SDK: WRITE / READ / DELETE OK")
