import os
import time
import logging
import socket
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError
from PyPDF2 import PdfReader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ELASTICSEARCH_PORT = int(os.environ.get("ELASTICSEARCH_PORT", 9200))
INDEX_NAME = "pdf_index"
MAX_RETRIES = 10 
RETRY_DELAY = 10  # seconds

def check_elasticsearch_connection():
    """Check if Elasticsearch port is open before attempting connection"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((ELASTICSEARCH_HOST, ELASTICSEARCH_PORT))
        sock.close()
        return result == 0
    except socket.error as e:
        logger.error(f"Socket error while checking Elasticsearch: {e}")
        return False

def wait_for_elasticsearch():
    """Wait for Elasticsearch to become available"""
    logger.info(f"Waiting for Elasticsearch at {ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}")
    
    for attempt in range(MAX_RETRIES):
        if check_elasticsearch_connection():
            try:
                es = Elasticsearch([{
                    "host": ELASTICSEARCH_HOST,
                    "port": ELASTICSEARCH_PORT,
                    "scheme": "http"
                }], request_timeout=30)
                
                if es.ping():
                    health = es.cluster.health()
                    logger.info(f"Successfully connected to Elasticsearch. Cluster health: {health['status']}")
                    return es
                
            except Exception as e:
                logger.warning(f"Elasticsearch ping failed on attempt {attempt + 1}: {e}")
        
        if attempt < MAX_RETRIES - 1:
            logger.info(f"Retrying in {RETRY_DELAY} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
    
    raise ConnectionError(f"Could not connect to Elasticsearch after {MAX_RETRIES} attempts")

def create_index(es):
    """Create index if it doesn't exist"""
    try:
        if not es.indices.exists(index=INDEX_NAME):
            es.indices.create(
                index=INDEX_NAME,
                body={
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0  # Set to 0 for single-node setup
                    },
                    "mappings": {
                        "properties": {
                            "filename": {"type": "keyword"},
                            "page_number": {"type": "integer"},
                            "content": {"type": "text"}
                        }
                    }
                }
            )
            logger.info(f"Created index: {INDEX_NAME}")
        else:
            logger.info(f"Index {INDEX_NAME} already exists")
    except Exception as e:
        logger.error(f"Error creating index: {e}")
        raise

def is_file_indexed(es, filename):
    """Check if a file is already indexed"""
    try:
        # First verify the index exists
        if not es.indices.exists(index=INDEX_NAME):
            return False
            
        # Search for the exact filename
        result = es.search(
            index=INDEX_NAME,
            body={
                "size": 0,
                "query": {
                    "term": {
                        "filename": filename
                    }
                }
            }
        )
        
        total_hits = result['hits']['total']['value']
        if total_hits > 0:
            logger.info(f"Found {total_hits} existing pages for {filename}")
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error checking if file is indexed ({filename}): {e}")
        # If we can't verify, assume not indexed to be safe
        return False

def index_pdf_content(es, pdf_path):
    """Index a single PDF file"""
    filename = os.path.basename(pdf_path)
    
    # Check if file is already indexed
    if is_file_indexed(es, filename):
        logger.info(f"Skipping {filename} - already indexed")
        return
        
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            num_pages = len(reader.pages)
            logger.info(f"Processing {filename} ({num_pages} pages)")

            for page_num in range(num_pages):
                try:
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    
                    if not text.strip():
                        logger.warning(f"Empty text on page {page_num + 1}")
                        continue
                        
                    document = {
                        "filename": filename,
                        "page_number": page_num + 1,
                        "content": text
                    }
                    
                    es.index(index=INDEX_NAME, body=document)
                    logger.info(f"Indexed page {page_num + 1}/{num_pages} from {filename}")

                except Exception as e:
                    logger.error(f"Error processing page {page_num + 1} of {filename}: {e}")

    except Exception as e:
        logger.error(f"Error processing {pdf_path}: {e}")

def main():
    try:
        # First check if PDFs directory exists
        pdf_directory = "pdfs"
        if not os.path.exists(pdf_directory):
            logger.error(f"Directory not found: {pdf_directory}")
            return

        # Then check if there are any PDFs
        pdf_files = [f for f in os.listdir(pdf_directory) if f.lower().endswith('.pdf')]
        if not pdf_files:
            logger.error(f"No PDF files found in {pdf_directory}")
            return

        # Now try to connect to Elasticsearch
        es = wait_for_elasticsearch()
        create_index(es)
        
        # Process PDF files
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        for filename in pdf_files:
            pdf_path = os.path.join(pdf_directory, filename)
            index_pdf_content(es, pdf_path)
            
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()