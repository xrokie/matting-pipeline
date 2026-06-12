import argparse
import json

from services.mask_service.project_store import MaskProjectStore
from services.mask_service.sam3_mask_service import SAM3MaskService


def print_state(state):
    print(json.dumps(state, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("--project", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--background", default=None)

    p = sub.add_parser("set-subject-text")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("set-subject-box")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--box", nargs=4, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("set-subject-point")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--point", nargs=2, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-foreground-text")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-foreground-box")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--box", nargs=4, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-foreground-point")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--point", nargs=2, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-mask-text")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-mask-point")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--point", nargs=2, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-mask-box")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--box", nargs=4, type=int, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-target-text")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-target-box")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--box", nargs=4, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("add-target-point")
    p.add_argument("--project", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--point", nargs=2, required=True)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("undo-foreground")
    p.add_argument("--project", required=True)

    p = sub.add_parser("undo-mask")
    p.add_argument("--project", required=True)

    p = sub.add_parser("state")
    p.add_argument("--project", required=True)

    args = parser.parse_args()
    store = MaskProjectStore(args.project)

    if args.command == "init":
        state = store.init_from_video(args.video, args.background)
        print_state(state)
        return

    if args.command == "state":
        print_state(store.load_state())
        return

    if args.command == "undo-foreground":
        service = SAM3MaskService(checkpoint="", device="cpu")
        state = service.undo_foreground(store)
        print_state(state)
        return

    if args.command == "undo-mask":
        service = SAM3MaskService(checkpoint="", device="cpu")
        state = service.undo_mask(store)
        print_state(state)
        return

    service = SAM3MaskService(checkpoint=args.checkpoint, device=args.device)
    state = store.load_state()
    first_frame = store.resolve_path(state["first_frame"], "inputs/first_frame.png")

    if args.command == "set-subject-text":
        mask = service.predict_text_mask(first_frame, args.text)
        if mask is None:
            raise RuntimeError("No mask generated for subject text")
        state = service.save_subject(store, mask, {"mode": "text", "text": args.text})
        print_state(state)
        return

    if args.command == "set-subject-box":
        mask = service.predict_box_mask(first_frame, args.box)
        if mask is None:
            raise RuntimeError("No mask generated for subject box")
        state = service.save_subject(store, mask, {"mode": "box", "box": args.box})
        print_state(state)
        return

    if args.command == "set-subject-point":
        mask = service.predict_point_mask(first_frame, args.point)
        if mask is None:
            raise RuntimeError("No mask generated for subject point")
        state = service.save_subject(store, mask, {"mode": "point", "point": args.point})
        print_state(state)
        return

    if args.command == "add-foreground-text":
        mask = service.predict_text_mask(first_frame, args.text)
        if mask is None:
            raise RuntimeError("No mask generated for foreground text")
        state = service.add_foreground(store, mask, {"mode": "text", "text": args.text})
        print_state(state)
        return

    if args.command == "add-foreground-box":
        mask = service.predict_box_mask(first_frame, args.box)
        if mask is None:
            raise RuntimeError("No mask generated for foreground box")
        state = service.add_foreground(store, mask, {"mode": "box", "box": args.box})
        print_state(state)
        return

    if args.command == "add-foreground-point":
        mask = service.predict_point_mask(first_frame, args.point)
        if mask is None:
            raise RuntimeError("No mask generated for foreground point")
        state = service.add_foreground(store, mask, {"mode": "point", "point": args.point})
        print_state(state)
        return

    if args.command == "add-mask-text":
        mask = service.predict_text_mask(first_frame, args.text)
        if mask is None:
            raise RuntimeError("No mask generated for retained text")
        state = service.add_retained_mask(store, mask, {"mode": "text", "text": args.text})
        print_state(state)
        return

    if args.command == "add-mask-point":
        mask = service.predict_point_mask(first_frame, args.point)
        if mask is None:
            raise RuntimeError("No mask generated for retained point")
        state = service.add_retained_mask(store, mask, {"mode": "point", "point": args.point})
        print_state(state)
        return

    if args.command == "add-mask-box":
        mask = service.predict_box_mask(first_frame, args.box)
        if mask is None:
            raise RuntimeError("No mask generated for retained box")
        state = service.add_retained_mask(store, mask, {"mode": "box", "box": args.box})
        print_state(state)
        return

    if args.command == "add-target-text":
        mask = service.predict_text_mask(first_frame, args.text)
        if mask is None:
            raise RuntimeError("No mask generated for target text")
        state = service.add_target(store, mask, {"mode": "text", "text": args.text})
        print_state(state)
        return

    if args.command == "add-target-box":
        mask = service.predict_box_mask(first_frame, args.box)
        if mask is None:
            raise RuntimeError("No mask generated for target box")
        state = service.add_target(store, mask, {"mode": "box", "box": args.box})
        print_state(state)
        return

    if args.command == "add-target-point":
        mask = service.predict_point_mask(first_frame, args.point)
        if mask is None:
            raise RuntimeError("No mask generated for target point")
        state = service.add_target(store, mask, {"mode": "point", "point": args.point})
        print_state(state)
        return


if __name__ == "__main__":
    main()
