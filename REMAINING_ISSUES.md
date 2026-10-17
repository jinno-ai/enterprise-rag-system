**Title:** Address Remaining Test Failures in Integration and Unit Tests

**Description:**
During the refactoring of the logging system, several test failures were identified that are unrelated to the logging changes. These failures should be addressed in a separate issue to keep the concerns separate.

**Identified Failures:**

1.  **`openai.AuthenticationError` in Integration Tests:**
    *   **Error:** `openai.AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: dummy. ...`
    *   **Location:** `tests/integration/test_rag_integration.py`
    *   **Cause:** The integration tests are making live calls to the OpenAI API with a dummy API key.
    *   **Recommendation:** Mock the OpenAI API calls in the integration tests to avoid the need for a real API key.

2.  **`TypeError` in `RetrievalResult` Instantiation:**
    *   **Error:** `TypeError: RetrievalResult.__init__() missing 1 required positional argument: 'source'`
    *   **Location:** `tests/integration/test_rag_integration.py` and `tests/unit/test_rag_pipeline.py`
    *   **Cause:** The `RetrievalResult` dataclass requires a `source` argument, but some tests are not providing it.
    *   **Recommendation:** Update all instantiations of `RetrievalResult` in the tests to include the `source` argument.

3.  **`AssertionError` in Latency Calculation:**
    *   **Error:** `AssertionError: assert 0 > 0`
    *   **Location:** `tests/unit/test_rag_pipeline.py`
    *   **Cause:** The `latency_ms` is not being calculated correctly in the mocked test because `time.time` is not being patched to simulate the passage of time.
    *   **Recommendation:** Patch `time.time` in the test to simulate a delay and allow the latency to be calculated as a value greater than zero.
