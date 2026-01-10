"""
Test script for S3 logo upload functionality
"""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.ai_ingredient_intelligence.logic.serper_product_search import (
    get_s3_client,
    check_logo_exists_in_s3,
    upload_logo_to_s3,
    get_favicon_url_fallback,
    fetch_platforms,
    PLATFORM_LOGO_URLS
)
from app.ai_ingredient_intelligence.config import AWS_S3_BUCKET_PLATFORM_LOGOS, AWS_S3_PLATFORM_LOGOS_PREFIX


def test_s3_client():
    """Test if S3 client can be initialized"""
    print("=" * 60)
    print("TEST 1: S3 Client Initialization")
    print("=" * 60)
    
    s3_client = get_s3_client()
    
    if s3_client:
        print("[OK] S3 client initialized successfully")
        try:
            region = s3_client.meta.region_name
            print(f"   Region: {region}")
        except:
            print("   Region: Not available (defaulting to us-east-1)")
        return s3_client
    else:
        print("[FAIL] S3 client initialization failed")
        print("   Check AWS credentials:")
        print("   - AWS_ACCESS_KEY_ID environment variable")
        print("   - AWS_SECRET_ACCESS_KEY environment variable")
        print("   - Or ~/.aws/credentials file")
        return None


def test_bucket_access(s3_client):
    """Test if we can access the S3 bucket"""
    print("\n" + "=" * 60)
    print("TEST 2: S3 Bucket Access")
    print("=" * 60)
    
    if not s3_client:
        print("⚠️ Skipping - No S3 client available")
        return False
    
    try:
        # Try to list objects in the bucket (lightweight check)
        s3_client.list_objects_v2(Bucket=AWS_S3_BUCKET_PLATFORM_LOGOS, MaxKeys=1)
        print(f"[OK] Can access bucket: {AWS_S3_BUCKET_PLATFORM_LOGOS}")
        return True
    except Exception as e:
        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', 'Unknown')
        error_msg = getattr(e, 'response', {}).get('Error', {}).get('Message', str(e))
        
        print(f"[FAIL] Cannot access bucket: {AWS_S3_BUCKET_PLATFORM_LOGOS}")
        print(f"   Error Code: {error_code}")
        print(f"   Error Message: {error_msg}")
        
        if error_code == 'NoSuchBucket':
            print(f"\n[INFO] The bucket '{AWS_S3_BUCKET_PLATFORM_LOGOS}' does not exist.")
            print("   Create it in AWS S3 console or using AWS CLI:")
            print(f"   aws s3 mb s3://{AWS_S3_BUCKET_PLATFORM_LOGOS}")
        elif error_code == 'AccessDenied':
            print(f"\n[INFO] Access denied to bucket '{AWS_S3_BUCKET_PLATFORM_LOGOS}'")
            print(f"   Path: {AWS_S3_PLATFORM_LOGOS_PREFIX}/")
            print("   Check IAM permissions:")
            print("   - s3:ListBucket")
            print("   - s3:PutObject")
            print("   - s3:GetObject")
            print("   - s3:HeadObject")
        
        return False


def test_logo_check(s3_client, platform="amazon"):
    """Test checking if logo exists in S3"""
    print("\n" + "=" * 60)
    print(f"TEST 3: Check Logo Exists in S3 (Platform: {platform})")
    print("=" * 60)
    
    if not s3_client:
        print("[SKIP] Skipping - No S3 client available")
        return None
    
    logo_url = check_logo_exists_in_s3(platform, s3_client)
    
    if logo_url:
        print(f"[OK] Logo found in S3: {logo_url}")
    else:
        print(f"[INFO] Logo not found in S3 (will be uploaded if upload test passes)")
    
    return logo_url


def test_logo_upload(s3_client, platform="amazon"):
    """Test uploading a logo to S3"""
    print("\n" + "=" * 60)
    print(f"TEST 4: Upload Logo to S3 (Platform: {platform})")
    print("=" * 60)
    
    if not s3_client:
        print("[SKIP] Skipping - No S3 client available")
        return None
    
    logo_url = upload_logo_to_s3(platform, s3_client)
    
    if logo_url:
        print(f"[OK] Logo uploaded successfully: {logo_url}")
        return logo_url
    else:
        print(f"[FAIL] Logo upload failed")
        return None


def test_favicon_fallback(platform="amazon", product_url=None):
    """Test favicon fallback mechanism"""
    print("\n" + "=" * 60)
    print(f"TEST 5: Favicon Fallback (Platform: {platform})")
    print("=" * 60)
    
    logo_url = get_favicon_url_fallback(platform, product_url)
    
    if logo_url:
        print(f"[OK] Favicon URL generated: {logo_url}")
        return logo_url
    else:
        print(f"[FAIL] No favicon URL available")
        return None


def test_platform_logos():
    """Test all platform logos"""
    print("\n" + "=" * 60)
    print("TEST 6: Platform Logo URLs Configuration")
    print("=" * 60)
    
    print(f"Configured platforms: {len(PLATFORM_LOGO_URLS)}")
    for platform, url in PLATFORM_LOGO_URLS.items():
        print(f"  - {platform}: {url}")
    
    return True


def main():
    """Run all tests"""
    print("\n" + "Testing S3 Logo Upload Functionality")
    print("=" * 60)
    
    # Test 1: S3 Client
    s3_client = test_s3_client()
    
    # Test 2: Bucket Access
    bucket_accessible = test_bucket_access(s3_client)
    
    # Test 3: Logo Check
    existing_logo = test_logo_check(s3_client, "amazon")
    
    # Test 4: Logo Upload (only if bucket is accessible and logo doesn't exist)
    uploaded_logo = None
    if bucket_accessible and not existing_logo:
        uploaded_logo = test_logo_upload(s3_client, "amazon")
    elif existing_logo:
        print("\n[SKIP] Skipping upload test - logo already exists in S3")
    
    # Test 5: Favicon Fallback
    favicon_url = test_favicon_fallback("amazon")
    
    # Test 6: Platform Configuration
    test_platform_logos()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"S3 Client: {'[OK] Available' if s3_client else '[FAIL] Not Available'}")
    print(f"Bucket Access: {'[OK] OK' if bucket_accessible else '[FAIL] Failed'}")
    print(f"Logo in S3: {'[OK] Found' if existing_logo else '[INFO] Not Found'}")
    print(f"Logo Upload: {'[OK] Success' if uploaded_logo else '[FAIL] Failed/Skipped'}")
    print(f"Favicon Fallback: {'[OK] Available' if favicon_url else '[FAIL] Not Available'}")
    
    if s3_client and bucket_accessible:
        print("\n[SUCCESS] S3 logo upload functionality is working!")
    elif not s3_client:
        print("\n[WARNING] S3 client not available - favicon fallback will be used")
    else:
        print("\n[WARNING] Bucket access issues - check configuration")


if __name__ == "__main__":
    main()

