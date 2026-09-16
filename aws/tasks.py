import logging, boto3, os, json
from datetime import datetime, timedelta
from celery import shared_task
from rbzk.settings import AWS_STORAGE_BUCKET_NAME, AWS_S3_CUSTOM_DOMAIN, AWS_ACCESS_KEY_ID,\
     AWS_SECRET_ACCESS_KEY, AWS_S3_REGION_NAME, BASE_DIR, TEMP_UPLOADS

logger = logging.getLogger(__name__)

s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_S3_REGION_NAME
)

DEBUG = os.environ.get("DEBUG")

@shared_task(name='low_priority:aws_upload_price_log', reject_on_worker_lost=False)
def aws_upload_price_log(price_data_q, product_id):
    """
    Process price data by appending to daily files and uploading completed files to S3.
    
    Args:
        price_data (dict): Dictionary containing price data with 'time' key
    """
    data_time = None
    file_exists = None
    try:
        # Parse the time from price_data
        if len(price_data_q) > 0:
            if isinstance(price_data_q[0]['time'], str):
                data_time = datetime.fromisoformat(price_data_q[0]['time'])
            else:
                data_time = price_data_q[0]['time']
            
            # Format the date for filename (you can adjust format as needed)
            date_str = data_time.strftime('%Y-%m-%d')
            
            # Construct the file path
            file_name = f"{date_str}-{product_id}.txt"
            dir_path = os.path.join(BASE_DIR, TEMP_UPLOADS)
            file_path = os.path.join(BASE_DIR, TEMP_UPLOADS, file_name)
            if not os.path.exists(dir_path):
                os.mkdir(dir_path) 
            # Check if file exists

            file_exists = os.path.exists(file_path)
            
            # Append data to file (create if doesn't exist)
            with open(file_path, 'a') as f:
                # Convert price_data to JSON string and add newline
                for price_msg in price_data_q:
                    json_line = json.dumps(price_msg)
                    f.write(json_line + '\n')
                f.close()
            
            # print(f"Successfully appended data to {file_path}")
        
        # If this is a new file, check for yesterday's file
        if not file_exists:
            # Calculate yesterday's date
            yesterday = data_time - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            yesterday_file = f"{yesterday_str}-{product_id}.txt"
            yesterday_path = os.path.join(BASE_DIR, TEMP_UPLOADS, yesterday_file)
            
            # Check if yesterday's file exists
            if os.path.exists(yesterday_path):
                
                # Upload to S3
                s3_key = f"price-logs/{product_id}/{yesterday_file}"
                if not DEBUG: 
                    try:
                        # Upload file to S3
                        s3_client.upload_file(
                            yesterday_path,
                            AWS_STORAGE_BUCKET_NAME,
                            s3_key
                        )
                        logger.info(f"Successfully uploaded {yesterday_file} to S3 bucket {AWS_STORAGE_BUCKET_NAME}")
                        
                        # Delete the local file after successful upload
                        os.remove(yesterday_path)
                        logger.info(f"Successfully deleted local file: {yesterday_path}")
                        
                    except Exception as e:
                        logger.error(f"Error uploading to S3: {str(e)}")
                        # Don't delete the file if upload failed
                        raise
            else:
                logger.warning(f"Yesterday's file not found: {yesterday_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing price data: {str(e)}")
        # Celery will mark the task as failed and can retry based on configuration
        raise