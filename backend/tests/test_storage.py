"""Storage: spots, what's in them (coins and bullion, with positions), the forms, and printouts."""

from test_api import coin_payload


def _spot(authed, name="Dansco Peace Album", notes=None):
    r = authed.post("/api/storage/spots", json={"name": name, "notes": notes})
    assert r.status_code == 201, r.text
    return r.json()


def test_storage_spots(authed, morgan_collection):
    album = _spot(authed, notes="In the safe")
    assert authed.post("/api/storage/spots", json={"name": "Dansco Peace Album"}).status_code == 409
    box = _spot(authed, "Box #12")

    # From the coin form: stored with a position.
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], storage_id=album["id"], storage_position="Page 2, hole 10"))
    assert r.status_code == 201, r.text
    c1 = r.json()
    assert (c1["storage_name"], c1["storage_position"]) == ("Dansco Peace Album", "Page 2, hole 10")
    # From the storage page.
    c2 = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1882)).json()
    d = authed.post(f"/api/storage/spots/{album['id']}/items",
                    json={"kind": "coin", "inventory_number": c2["inventory_number"], "position": "Page 2, hole 9"}).json()
    assert [x["inventory_number"] for x in d["items"]] == [c2["inventory_number"], c1["inventory_number"]]  # 9 before 10
    assert d["coin_count"] == 2

    # Bullion too.
    col = authed.post("/api/bullion/collections", json={"name": "Silver", "metal": "silver"}).json()
    bar = authed.post("/api/bullion/items", json={"collection_id": col["id"], "description": "10 oz bar", "weight": "10",
                                                  "weight_unit": "ozt", "purity": "0.999", "storage_id": box["id"]})
    assert bar.status_code == 201 and bar.json()["storage_name"] == "Box #12", bar.text
    spots = {s["name"]: s for s in authed.get("/api/storage/spots").json()}
    assert spots["Box #12"]["bullion_count"] == 1 and spots["Box #12"]["value"] == "499.50"  # 9.99 oz at $50

    # Moving a coin to another spot; a coin at grading keeps its spot.
    authed.post(f"/api/storage/spots/{box['id']}/items", json={"kind": "coin", "inventory_number": c2["inventory_number"]})
    assert authed.get(f"/api/storage/spots/{album['id']}").json()["coin_count"] == 1
    body = coin_payload(morgan_collection["id"], cert_number=c1["cert_number"], storage_id=album["id"],
                        storage_position="Page 2, hole 10", location="grading", grading={"new_company": "NGC"})
    assert authed.put(f"/api/coins/{c1['inventory_number']}", json=body).json()["storage_name"] == "Dansco Peace Album"
    assert authed.get(f"/api/storage/spots/{album['id']}").json()["items"][0]["at_grading"] is True

    # Printouts: with values, and a checklist.
    for values in ("true", "false"):
        r = authed.get(f"/api/storage/spots/{album['id']}/report?values={values}")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert ("Inventory" if values == "true" else "Checklist") in r.headers["content-disposition"]

    # Deleting a spot keeps the coins, just not stored anywhere.
    assert authed.delete(f"/api/storage/spots/{album['id']}").status_code == 204
    assert authed.get(f"/api/coins/{c1['inventory_number']}").json()["storage_id"] is None


def test_storage_is_private(authed, morgan_collection, client):
    spot = _spot(authed)
    other = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], storage_id=999)).status_code
    assert other == 404
    assert authed.get(f"/api/storage/spots/{spot['id'] + 100}").status_code == 404
