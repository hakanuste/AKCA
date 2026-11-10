import argparse, json
from .db import connect
from .ingest import import_items
from .index import check_weights, calculate_month

def main():
 parser=argparse.ArgumentParser(prog="akca")
 sub=parser.add_subparsers(dest="cmd",required=True)
 sub.add_parser("init"); sub.add_parser("import-items"); sub.add_parser("item-count"); sub.add_parser("check-weights")
 c=sub.add_parser("calculate-index"); c.add_argument("period")
 args=parser.parse_args()
 if args.cmd in ("init","import-items"): print(f"2022 madde kaydı: {import_items()}")
 elif args.cmd=="item-count":
  conn=connect(); print(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]); conn.close()
 elif args.cmd=="check-weights": print(json.dumps(check_weights(),ensure_ascii=False,indent=2))
 elif args.cmd=="calculate-index": print(json.dumps(calculate_month(args.period),ensure_ascii=False,indent=2))
