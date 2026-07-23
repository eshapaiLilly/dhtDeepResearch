import net_bootstrap, live_clients, requests
headers = {"x-api-key": live_clients.S2_API_KEY} if live_clients.S2_API_KEY else {}
resp = requests.get(
    f"{live_clients.S2_BASE}/paper/search/bulk",
    params={"query": '"test"', "fields": "title"},
    headers=headers, timeout=15,
)
print(resp.status_code)
print(resp.text)
