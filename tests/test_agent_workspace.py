from mindmemory_client.agent_workspace import gogs_username, memory_repo_ssh_url


def test_gogs_username() -> None:
    assert gogs_username("7ef010e5-ba32-40e5-b13e-a71587041616") == "7ef010e5ba3240e5b13ea71587041616"


def test_memory_repo_ssh_url() -> None:
    u = "7ef010e5-ba32-40e5-b13e-a71587041616"
    url = memory_repo_ssh_url(u, "my-agent", ssh_host="gogs.example.com")
    assert url == "git@gogs.example.com:7ef010e5ba3240e5b13ea71587041616/my-agent.git"
