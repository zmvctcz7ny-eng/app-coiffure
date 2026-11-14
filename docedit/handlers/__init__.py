from . import docx_h, image, pdf, xlsx_h

HANDLERS = {"pdf": pdf, "image": image, "scan": image, "docx": docx_h, "xlsx": xlsx_h}

KIND_LABELS = {"pdf": "PDF", "image": "Image", "scan": "Document scanné", "docx": "Word", "xlsx": "Excel"}


def handler_for(doc):
    return HANDLERS[doc.kind]
