from  tools.ssh_tols import ssh_execute


result = ssh_execute(
    "R1",
    "/interface print"
)

print(result["output"])