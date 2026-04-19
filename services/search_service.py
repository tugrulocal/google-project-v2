"""
Search Service - Handles search queries and ranking.

This service provides:
- Index file searching
- Relevance-based ranking
- Pagination support
- Multiple sort options
"""

import os
import re
import math
import random
from typing import Dict, List, Optional, Tuple


class SearchService:
    """
    Service for searching and ranking indexed content.

    Ranking Algorithm:
    - relevance = frequency × (1 / (1 + depth × 0.1)) × match_quality
    - Supports sorting by: relevance, frequency, depth
    """

    STORAGE_DIR = os.path.join("data", "storage")

    def __init__(self):
        """Initialize the search service."""
        os.makedirs(self.STORAGE_DIR, exist_ok=True)

    def search(
        self,
        query: str,
        page_limit: int = 10,
        page_offset: int = 0,
        sort_by: str = "relevance"
    ) -> Dict:
        """
        Search the index for matching entries.

        Args:
            query: Search query string (space-separated words)
            page_limit: Maximum results per page
            page_offset: Number of results to skip
            sort_by: Sort method - "relevance", "frequency", or "depth"

        Returns:
            Search results with metadata
        """
        if not query or not query.strip():
            return {
                "query": "",
                "results": [],
                "triples": [],
                "total_results": 0,
                "page_limit": page_limit,
                "page_offset": page_offset,
                "sort_by": sort_by,
                "error": "Empty query"
            }

        # Tokenize query
        query_words = self._tokenize_query(query)
        if not query_words:
            return {
                "query": query,
                "results": [],
                "triples": [],
                "total_results": 0,
                "page_limit": page_limit,
                "page_offset": page_offset,
                "sort_by": sort_by,
                "query_words": []
            }

        # We need N (total unique URLs) for IDF calculation
        index_stats = self.get_index_stats()
        N = max(1, index_stats.get("unique_urls", 1))

        # Collect results from index files
        word_results = []
        files_searched = 0
        word_idf_map = {}

        for word in query_words:
            results, searched = self._search_word(word)
            word_results.append(results)
            files_searched += searched
            
            # Document frequency (DF) for this word is the number of distinct URLs that contain it
            df = len(set(res["url"] for res in results))
            # Inverse Document Frequency (TF-IDF): log(N / DF)
            idf = math.log(N / (df if df > 0 else 1)) + 1.0
            word_idf_map[word] = idf

        # AND Logic: Intersect URLs across all query words
        if not word_results:
            common_urls = set()
        else:
            common_urls = {res["url"] for res in word_results[0]}
            for results in word_results[1:]:
                common_urls.intersection_update({res["url"] for res in results})

        # Calculate relevance scores using TF-IDF and group by URL
        url_combined_results = {}
        for results_list in word_results:
            for result in results_list:
                url = result.get("url", "")
                if url in common_urls:
                    if url not in url_combined_results:
                        # Initialize combined result
                        url_combined_results[url] = result.copy()
                        url_combined_results[url]["score"] = 0.0
                    
                    # Find which query word it matched
                    word = result.get("word", "")
                    matched_q_word = next((qw for qw in query_words if word.startswith(qw)), query_words[0])
                    idf = word_idf_map.get(matched_q_word, 1.0)
                    
                    # Original single score * idf
                    tf_idf_score = self._calculate_score(result, query_words) * idf
                    url_combined_results[url]["score"] += tf_idf_score

        # Round the final combined scores to 2 decimal places
        for url in url_combined_results:
            url_combined_results[url]["score"] = round(url_combined_results[url]["score"], 2)

        unique_results = list(url_combined_results.values())

        # Sort results
        all_results = self._sort_results(unique_results, sort_by)

        # Pagination
        total_results = len(all_results)
        paginated_results = all_results[page_offset:page_offset + page_limit]

        # Keep backward compatibility while exposing HW2-required triples.
        enriched_results = []
        for result in paginated_results:
            item = result.copy()
            item["relevant_url"] = item.get("url", "")
            item["origin_url"] = item.get("origin", "")
            enriched_results.append(item)

        triples = [
            [item.get("relevant_url", ""), item.get("origin_url", ""), item.get("depth", 0)]
            for item in enriched_results
        ]

        return {
            "query": query,
            "query_words": query_words,
            "results": enriched_results,
            "triples": triples,
            "total_results": total_results,
            "page_limit": page_limit,
            "page_offset": page_offset,
            "sort_by": sort_by,
            "files_searched": files_searched
        }

    def _tokenize_query(self, query: str) -> List[str]:
        """
        Tokenize query string into search words.

        Args:
            query: Raw query string

        Returns:
            List of lowercase words (2+ chars)
        """
        # Extract words (2+ Unicode word characters)
        words = re.findall(r'\b\w{2,}\b', query.lower(), re.UNICODE)
        # Remove duplicates while preserving order
        seen = set()
        unique_words = []
        for word in words:
            if word not in seen:
                seen.add(word)
                unique_words.append(word)
        return unique_words

    def _search_word(self, word: str) -> Tuple[List[Dict], int]:
        """
        Search for a word in the appropriate index file.

        Args:
            word: Word to search for

        Returns:
            Tuple of (list of results, number of files searched)
        """
        results = []
        files_searched = 0

        # Determine which file to search
        first_char = word[0].lower()
        if first_char.isalpha():
            letter = first_char
        else:
            letter = '0'

        filepath = os.path.join(self.STORAGE_DIR, f"{letter}.data")

        if not os.path.exists(filepath):
            return [], 0

        files_searched = 1

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # Parse line: word url origin depth frequency
                    parts = line.split(' ')
                    if len(parts) >= 5:
                        indexed_word = parts[0]
                        url = parts[1]
                        origin = parts[2]
                        depth = int(parts[3])
                        frequency = int(parts[4])

                        # Check for match (exact or prefix)
                        if indexed_word == word or indexed_word.startswith(word):
                            results.append({
                                "word": indexed_word,
                                "url": url,
                                "origin": origin,
                                "depth": depth,
                                "frequency": frequency,
                                "match_type": "exact" if indexed_word == word else "prefix"
                            })
        except Exception:
            pass

        return results, files_searched

    def _calculate_score(self, result: Dict, query_words: List[str]) -> float:
        """
        Calculate relevance score for a result.

        Formula:
        score = frequency × depth_boost × match_quality

        Where:
        - depth_boost = 1 / (1 + depth × 0.1)
        - match_quality = 1.0 for exact, 0.8 for prefix

        Args:
            result: Search result dict
            query_words: List of query words

        Returns:
            Relevance score (float)
        """
        frequency = result.get("frequency", 1)
        depth = result.get("depth", 0)
        match_type = result.get("match_type", "exact")

        # Depth boost (closer to seed = higher score)
        depth_boost = 1.0 / (1.0 + depth * 0.1)

        # Match quality
        match_quality = 1.0 if match_type == "exact" else 0.8

        # Base score
        score = frequency * depth_boost * match_quality

        # Boost for multiple query word matches (if applicable)
        word = result.get("word", "")
        word_match_count = sum(1 for qw in query_words if word.startswith(qw))
        if word_match_count > 1:
            score *= (1 + 0.2 * (word_match_count - 1))

        return round(score, 2)

    def _sort_results(self, results: List[Dict], sort_by: str) -> List[Dict]:
        """
        Sort results by specified criteria.

        Args:
            results: List of result dicts
            sort_by: Sort method

        Returns:
            Sorted list
        """
        if sort_by == "frequency":
            return sorted(results, key=lambda x: x.get("frequency", 0), reverse=True)
        elif sort_by == "depth":
            return sorted(results, key=lambda x: x.get("depth", 999))
        else:  # relevance (default)
            return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

    def get_random_word(self) -> Optional[str]:
        """
        Get a random word from the index.

        Returns:
            Random indexed word or None
        """
        if not os.path.exists(self.STORAGE_DIR):
            return None

        # List all data files
        files = [f for f in os.listdir(self.STORAGE_DIR) if f.endswith('.data')]
        if not files:
            return None

        # Pick a random file
        random_file = random.choice(files)
        filepath = os.path.join(self.STORAGE_DIR, random_file)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                return None

            # Pick a random line
            random_line = random.choice(lines).strip()
            if random_line:
                parts = random_line.split(' ')
                if parts:
                    return parts[0]  # Return the word
        except Exception:
            pass

        return None

    def get_index_stats(self) -> Dict:
        """
        Get statistics about the search index.

        Returns:
            Index statistics dict
        """
        stats = {
            "total_entries": 0,
            "unique_words": set(),
            "unique_urls": set(),
            "files": {},
            "storage_size_bytes": 0
        }

        if not os.path.exists(self.STORAGE_DIR):
            stats["unique_words"] = 0
            stats["unique_urls"] = 0
            return stats

        for filename in os.listdir(self.STORAGE_DIR):
            if filename.endswith('.data'):
                filepath = os.path.join(self.STORAGE_DIR, filename)
                file_stats = {"entries": 0, "size_bytes": os.path.getsize(filepath)}
                stats["storage_size_bytes"] += file_stats["size_bytes"]

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            parts = line.strip().split(' ')
                            if len(parts) >= 5:
                                file_stats["entries"] += 1
                                stats["total_entries"] += 1
                                stats["unique_words"].add(parts[0])
                                stats["unique_urls"].add(parts[1])
                except Exception:
                    pass

                stats["files"][filename] = file_stats

        # Convert sets to counts
        stats["unique_words"] = len(stats["unique_words"])
        stats["unique_urls"] = len(stats["unique_urls"])

        return stats


# Singleton instance
_search_instance: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Get or create the search service singleton."""
    global _search_instance
    if _search_instance is None:
        _search_instance = SearchService()
    return _search_instance
