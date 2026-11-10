from akca.ingest import import_items
from akca.index import check_weights

def test_items_import_and_missing_weights_are_blocked(tmp_path):
 db=tmp_path/"test.db"
 count=import_items(db_path=db)
 assert count == 409
 status=check_weights(db_path=db)
 assert status["item_count"] == 409
 assert status["ready"] is False
 assert len(status["missing_or_unverified"]) == 409
