"""
Google in a Day - Flask REST API

This module provides the REST API for the mini search engine.
All endpoints follow the Gold Standard specification.

Endpoints:
- POST /crawler/create     - Start new crawler
- GET  /crawler/status/<id> - Get crawler status
- GET  /crawler/list       - List all crawlers
- POST /crawler/pause/<id>  - Pause crawler
- POST /crawler/resume/<id> - Resume crawler
- POST /crawler/stop/<id>   - Stop crawler
- POST /crawler/resume-from-files/<id> - Resume from saved state
- POST /crawler/clear      - Clear all data
- GET  /crawler/stats      - Get statistics
- GET  /search             - Search indexed content
- GET  /search/random      - Get random word
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from services.crawler_service import get_crawler_service
from services.search_service import get_search_service

# Initialize Flask app
app = Flask(__name__, static_folder='demo')
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuration
HOST = "0.0.0.0"
PORT = 3600


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error", "details": str(e)}), 500


# =============================================================================
# Crawler Endpoints
# =============================================================================

@app.route('/crawler/create', methods=['POST'])
def create_crawler():
    """
    Start a new crawler job.

    Request Body (JSON):
    {
        "origin": "https://example.com",  # Required
        "max_depth": 3,                   # Optional (1-1000, default: 3)
        "hit_rate": 100.0,                # Optional (0.1-1000, default: 100)
        "max_queue_capacity": 10000,      # Optional (100-100000, default: 10000)
        "max_urls_to_visit": 1000,        # Optional (0-10000, default: 1000)
        "same_domain_only": true,         # Optional (default: true)
        "include_subdomains": false,      # Optional (default: false)
        "allowed_paths": ["/docs", "/api"],  # Optional
        "blocked_patterns": ["tracking", "ad"]  # Optional
    }

    Response 201:
    {
        "crawler_id": "1679404800_12345",
        "status": "Active"
    }
    """
    try:
        data = request.get_json() or {}

        # Validate required field
        origin = data.get('origin')
        if not origin:
            return jsonify({"error": "Missing required field: origin"}), 400

        # Optional parameters with defaults
        max_depth = data.get('max_depth', 3)
        hit_rate = data.get('hit_rate', 100.0)
        max_queue_capacity = data.get('max_queue_capacity', 10000)
        max_urls_to_visit = data.get('max_urls_to_visit', 1000)

        # Domain filtering parameters
        same_domain_only = data.get('same_domain_only', True)
        include_subdomains = data.get('include_subdomains', False)
        allowed_paths = data.get('allowed_paths')
        blocked_patterns = data.get('blocked_patterns')

        # Parse blocked_patterns if string (comma-separated)
        if isinstance(blocked_patterns, str):
            blocked_patterns = [p.strip() for p in blocked_patterns.split(',') if p.strip()]

        # Create crawler
        service = get_crawler_service()
        result = service.create_crawler(
            origin=origin,
            max_depth=max_depth,
            hit_rate=hit_rate,
            max_queue_capacity=max_queue_capacity,
            max_urls_to_visit=max_urls_to_visit,
            same_domain_only=same_domain_only,
            include_subdomains=include_subdomains,
            allowed_paths=allowed_paths,
            blocked_patterns=blocked_patterns
        )

        return jsonify(result), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Failed to create crawler", "details": str(e)}), 500


@app.route('/crawler/status/<crawler_id>', methods=['GET'])
def get_crawler_status(crawler_id):
    """
    Get status of a specific crawler.

    Response 200:
    {
        "crawler_id": "...",
        "status": "Active",
        "origin": "https://...",
        "config": {...},
        "stats": {...},
        "logs": [...]
    }
    """
    try:
        service = get_crawler_service()
        status = service.get_crawler_status(crawler_id)

        if status is None:
            return jsonify({"error": f"Crawler {crawler_id} not found"}), 404

        return jsonify(status), 200

    except Exception as e:
        return jsonify({"error": "Failed to get status", "details": str(e)}), 500


@app.route('/crawler/list', methods=['GET'])
def list_crawlers():
    """
    List all crawlers.

    Response 200:
    [
        {"crawler_id": "...", "origin": "...", "status": "...", ...},
        ...
    ]
    """
    try:
        service = get_crawler_service()
        crawlers = service.list_crawlers()
        return jsonify(crawlers), 200

    except Exception as e:
        return jsonify({"error": "Failed to list crawlers", "details": str(e)}), 500


@app.route('/crawler/pause/<crawler_id>', methods=['POST'])
def pause_crawler(crawler_id):
    """
    Pause an active crawler.

    Response 200:
    {"status": "Paused"}
    """
    try:
        service = get_crawler_service()
        result = service.pause_crawler(crawler_id)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to pause crawler", "details": str(e)}), 500


@app.route('/crawler/resume/<crawler_id>', methods=['POST'])
def resume_crawler(crawler_id):
    """
    Resume a paused crawler.

    Response 200:
    {"status": "Active"}
    """
    try:
        service = get_crawler_service()
        result = service.resume_crawler(crawler_id)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to resume crawler", "details": str(e)}), 500


@app.route('/crawler/stop/<crawler_id>', methods=['POST'])
def stop_crawler(crawler_id):
    """
    Stop an active crawler.

    Response 200:
    {"status": "Stopped"}
    """
    try:
        service = get_crawler_service()
        result = service.stop_crawler(crawler_id)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to stop crawler", "details": str(e)}), 500


@app.route('/crawler/<crawler_id>', methods=['DELETE'])
def delete_crawler(crawler_id):
    """
    Delete a crawler and its associated files.

    Response 200:
    {
        "status": "deleted",
        "crawler_id": "...",
        "files_deleted": ["....data", "....logs", "....queue"]
    }
    """
    try:
        service = get_crawler_service()
        result = service.delete_crawler(crawler_id)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to delete crawler", "details": str(e)}), 500


@app.route('/crawler/resume-from-files/<crawler_id>', methods=['POST'])
def resume_from_files(crawler_id):
    """
    Resume a stopped crawler from saved state files.

    Response 200:
    {"status": "Active", "message": "Resumed from saved state"}
    """
    try:
        service = get_crawler_service()
        result = service.resume_from_files(crawler_id)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Failed to resume from files", "details": str(e)}), 500


@app.route('/crawler/clear', methods=['POST'])
def clear_all_data():
    """
    Clear all crawler data.

    Response 200:
    {"status": "success", "message": "All data cleared"}
    """
    try:
        service = get_crawler_service()
        result = service.clear_all_data()
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": "Failed to clear data", "details": str(e)}), 500


@app.route('/crawler/stats', methods=['GET'])
def get_statistics():
    """
    Get aggregate statistics.

    Response 200:
    {
        "total_crawlers": 3,
        "active_crawlers": 1,
        "total_urls_crawled": 2547,
        ...
    }
    """
    try:
        service = get_crawler_service()
        stats = service.get_statistics()
        return jsonify(stats), 200

    except Exception as e:
        return jsonify({"error": "Failed to get statistics", "details": str(e)}), 500


# =============================================================================
# Search Endpoints
# =============================================================================

@app.route('/search', methods=['GET'])
def search():
    """
    Search indexed content.

    Query Parameters:
    - query: Search query (required)
    - pageLimit: Results per page (default: 10)
    - pageOffset: Results to skip (default: 0)
    - sortBy: "relevance", "frequency", or "depth" (default: "relevance")

    Response 200:
    {
        "query": "python programming",
        "query_words": ["python", "programming"],
        "results": [...],
        "total_results": 156,
        "page_limit": 10,
        "page_offset": 0,
        "sort_by": "relevance"
    }
    """
    try:
        query = request.args.get('query', '')
        page_limit = int(request.args.get('pageLimit', 10))
        page_offset = int(request.args.get('pageOffset', 0))
        sort_by = request.args.get('sortBy', 'relevance')

        # Validate
        page_limit = max(1, min(page_limit, 100))
        page_offset = max(0, page_offset)
        if sort_by not in ('relevance', 'frequency', 'depth'):
            sort_by = 'relevance'

        service = get_search_service()
        results = service.search(
            query=query,
            page_limit=page_limit,
            page_offset=page_offset,
            sort_by=sort_by
        )

        return jsonify(results), 200

    except Exception as e:
        return jsonify({"error": "Search failed", "details": str(e)}), 500


@app.route('/search/random', methods=['GET'])
def random_word():
    """
    Get a random indexed word (I'm Feeling Lucky).

    Response 200:
    {"word": "algorithm"}
    """
    try:
        service = get_search_service()
        word = service.get_random_word()

        if word:
            return jsonify({"word": word}), 200
        else:
            return jsonify({"word": None, "message": "No indexed words available"}), 200

    except Exception as e:
        return jsonify({"error": "Failed to get random word", "details": str(e)}), 500


@app.route('/index/stats', methods=['GET'])
def index_stats():
    """
    Get search index statistics.

    Response 200:
    {
        "total_entries": 15000,
        "unique_words": 3500,
        "unique_urls": 450,
        ...
    }
    """
    try:
        service = get_search_service()
        stats = service.get_index_stats()
        return jsonify(stats), 200

    except Exception as e:
        return jsonify({"error": "Failed to get index stats", "details": str(e)}), 500


# =============================================================================
# Static File Serving (Dashboard)
# =============================================================================

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return send_from_directory('demo', 'crawler.html')


@app.route('/crawler')
def crawler_page():
    """Serve the crawler control page."""
    return send_from_directory('demo', 'crawler.html')


@app.route('/status')
def status_page():
    """Serve the status monitoring page."""
    return send_from_directory('demo', 'status.html')


@app.route('/search-page')
def search_page():
    """Serve the search page."""
    return send_from_directory('demo', 'search.html')


@app.route('/demo/<path:filename>')
def serve_demo(filename):
    """Serve static files from demo directory."""
    return send_from_directory('demo', filename)


# =============================================================================
# Health Check
# =============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "port": PORT}), 200


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║              GOOGLE IN A DAY - Mini Search Engine             ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║  API Server running at: http://localhost:{PORT}                 ║
    ║                                                               ║
    ║  Dashboard:    http://localhost:{PORT}/                         ║
    ║  API Docs:     See product_prd.md                             ║
    ║                                                               ║
    ║  Endpoints:                                                   ║
    ║    POST /crawler/create     - Start new crawler               ║
    ║    GET  /crawler/status/<id> - Get crawler status              ║
    ║    POST /crawler/pause/<id>  - Pause crawler                   ║
    ║    POST /crawler/resume/<id> - Resume crawler                  ║
    ║    POST /crawler/stop/<id>   - Stop crawler                    ║
    ║    GET  /search?query=...   - Search indexed content          ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=HOST, port=PORT, debug=True, threaded=True)
