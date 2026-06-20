import re

with open('app/core/vectordb.py', 'r') as f:
    content = f.read()

# 1. Move add_documents from abstract method to base class method with default implementation
# This avoids breaking other subclasses like PineconeVectorDB
content = content.replace(
    '    @abstractmethod\n    def add_documents(\n        self,\n        documents: List[str],\n        embeddings: List[List[float]],\n        metadatas: Optional[List[Dict[str, Any]]] = None\n    ) -> List[str]:\n        """Add documents to the vector database"""\n        pass',
    ''
)

base_impl = """
    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        \"\"\"Default implementation for adding documents\"\"\"
        import uuid

        ids = [str(uuid.uuid4()) for _ in range(len(documents))]

        if metadatas is None:
            metadatas = [{} for _ in range(len(documents))]

        # Copy metadatas to avoid modifying the input list in-place if it's shared
        metadatas = [m.copy() for m in metadatas]

        for i, doc in enumerate(documents):
            metadatas[i]['text'] = doc

        self.upsert(embeddings, ids, metadatas)
        return ids
"""

content = re.sub(
    r'(def get_stats\(self\) -> Dict\[str, Any\]:\n\s+"""Get database statistics"""\n\s+pass)',
    r'\1\n' + base_impl,
    content
)

# 2. Remove specific implementation from FAISSVectorDB to use base implementation
content = re.sub(
    r'    def add_documents\(\n\s+self,\n\s+documents: List\[str\],\n\s+embeddings: List\[List\[float\]\],\n\s+metadatas: Optional\[List\[Dict\[str, Any\]\]\] = None\n\s+\) -> List\[str\]:\n\s+"""Add documents to FAISS"""\n\s+import uuid\n\s+\n\s+ids = \[str\(uuid\.uuid4\(\)\) for _ in range\(len\(documents\)\)\]\n\s+\n\s+if metadatas is None:\n\s+metadatas = \[{} for _ in range\(len\(documents\)\)\]\n\s+\n\s+for i, doc in enumerate\(documents\):\n\s+metadatas\[i\]\[\'text\'\] = doc\n\s+\n\s+self\.upsert\(embeddings, ids, metadatas\)\n\s+return ids\n',
    '',
    content
)

with open('app/core/vectordb.py', 'w') as f:
    f.write(content)
