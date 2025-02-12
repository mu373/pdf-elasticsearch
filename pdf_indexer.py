import os
import time
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
from PyPDF2 import PdfReader

ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ELASTICSEARCH_PORT = int(os.environ.get("ELASTICSEARCH_PORT", 9200))
INDEX_NAME = "pdf_index"

def wait_for_elasticsearch():
    es = Elasticsearch([{"host": ELASTICSEARCH_HOST, "port": ELASTICSEARCH_PORT, "scheme": "http"}])
    while True:
        try:
            if es.ping():
                print("Elasticsearch is ready!")
                break
        except ConnectionError:
            print("Elasticsearch is not ready yet, waiting...")
            time.sleep(5)

es = Elasticsearch([{"host": ELASTICSEARCH_HOST, "port": ELASTICSEARCH_PORT, "scheme": "http"}])

def create_index():
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(
            index=INDEX_NAME,
            body={
                "mappings": {
                    "properties": {
                        "filename": {"type": "keyword"},
                        "page_number": {"type": "integer"},
                        "content": {"type": "text"}
                    }
                }
            }
        )

def index_pdf_content(pdf_path):
    filename = os.path.basename(pdf_path)
    
    search_result = es.search(
        index=INDEX_NAME,
        body={
            "query": {
                "term": {
                    "filename.keyword": filename
                }
            }
        }
    )

    if search_result['hits']['total']['value'] > 0:
        print(f"Skipping {filename} - already indexed")
        return

    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            num_pages = len(reader.pages)

            for page_num in range(num_pages):
                page = reader.pages[page_num]
                text = page.extract_text()

                document = {
                    "filename": filename,
                    "page_number": page_num + 1,
                    "content": text
                }

                es.index(index=INDEX_NAME, body=document)
                print(f"Indexed page {page_num + 1} from {pdf_path}")

    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")


def main():
    wait_for_elasticsearch()
    create_index()
    pdf_directory = "pdfs"
    for filename in os.listdir(pdf_directory):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(pdf_directory, filename)
            index_pdf_content(pdf_path)

if __name__ == "__main__":
    main()

