import argparse
import json

from .db import connect
from .index import calculate_month, check_weights
from .ingest import add_variant, import_items, set_item_weight
from .pricing import set_observation_status

def main():
    parser = argparse.ArgumentParser(prog="akca")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("import-items")
    sub.add_parser("item-count")
    sub.add_parser("check-weights")

    weight = sub.add_parser("set-item-weight")
    weight.add_argument("item_code")
    weight.add_argument("weight_percent", type=float)
    weight.add_argument("source")
    weight.add_argument("--verified", action="store_true")

    variant = sub.add_parser("add-variant")
    variant.add_argument("item_code")
    variant.add_argument("variant_key")
    variant.add_argument("label")
    variant.add_argument("within_item_weight_percent", type=float)
    variant.add_argument("source")
    variant.add_argument("--verified", action="store_true")

    review = sub.add_parser("review-observation")
    review.add_argument("observation_id", type=int)
    review.add_argument("status", choices=["approved", "rejected", "pending"])
    review.add_argument("--note", default=None)

    calc = sub.add_parser("calculate-index")
    calc.add_argument("period")
    args = parser.parse_args()

    if args.cmd in ("init", "import-items"):
        print(f"2022 madde kaydı: {import_items()}")
    elif args.cmd == "item-count":
        conn = connect()
        print(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
        conn.close()
    elif args.cmd == "check-weights":
        print(json.dumps(check_weights(), ensure_ascii=False, indent=2))
    elif args.cmd == "set-item-weight":
        set_item_weight(args.item_code, args.weight_percent, args.source, args.verified)
    elif args.cmd == "add-variant":
        add_variant(
            args.item_code, args.variant_key, args.label,
            args.within_item_weight_percent, args.source, args.verified,
        )
    elif args.cmd == "review-observation":
        set_observation_status(args.observation_id, args.status, args.note)
    elif args.cmd == "calculate-index":
        print(json.dumps(calculate_month(args.period), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
