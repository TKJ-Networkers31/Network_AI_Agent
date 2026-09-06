from tools.ssh.client import ssh_execute


result = ssh_execute(
    "R1",
    "/interface print"
)

if result["success"]:
    print(result["output"])
else:
    print(f"Gagal: {result['error']}")