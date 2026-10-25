"""One Markdown image contract for every card-returning entry."""
from pathlib import Path
from urllib.parse import quote


def _label(value):
    return str(value).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


def card_markup(card):
    path = card.get("delivery_image_absolute_path") or card.get("hero_image_absolute_path")
    if not path or card.get("images_ready") is False:
        return ""
    path = Path(path).resolve()
    if path.suffix.lower() != ".png" or not path.is_file():
        return ""
    label = card.get("display_number") or card.get("id") or "隐藏吃法"
    title = card.get("card_title") or card.get("name") or ""
    # WorkBuddy chat does not resolve bare filesystem paths. Its registered
    # local-file protocol renders PNGs inline without a service or upload.
    destination = "local-file://" + quote(path.as_posix(), safe="/:")
    return "![{} · {}]({})".format(_label(label), _label(title), destination)


def inline_response(result):
    """Attach exact final-answer blocks; an artifact registration is not an image render."""
    rendered, seen = [], set()
    for key in ("cards", "methods", "supplementary"):
        for card in result.get(key, []) or []:
            image = card_markup(card)
            card["image_markdown"] = image
            label = "{} · {}".format(card.get("display_number") or card.get("id", ""),
                                      card.get("card_title") or card.get("name", ""))
            card["inline_markdown"] = ("### " + label + "\n\n" + image) if image else ""
            if image and card.get("id") not in seen:
                seen.add(card.get("id")); rendered.append(card["inline_markdown"])
    result["response_markdown"] = "\n\n".join(rendered)
    result["inline_image_count"] = len(rendered)
    result["image_delivery_policy"] = "final_message_inline_markdown_required"
    return result
