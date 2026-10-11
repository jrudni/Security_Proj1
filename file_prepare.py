import hashlib

file_name = "firmware.txt"

def read_file(file_path):
    with open(file_path, 'rb') as f:
        return f.read()

def split_data(data, chunk_count):
    n = len(data)
    if chunk_count <= 0 or chunk_count > n:
        raise ValueError("chunk_count must be greater than 0 and less than length of file")
    
    return [
        data[i * n // chunk_count : (i + 1) * n // chunk_count]
        for i in range(chunk_count)
    ]

def calculate_sha256(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

class Node:
    def __init__(self, data, hash=None, left=None, right=None):
        self.data = data
        self.hash = hash or calculate_sha256(data)
        self.l = left
        self.r = right

class MerkleTree:
    def __init__(self, data_chunks: list[bytes]):
        if len(data_chunks) != 4 or any(not chunk for chunk in data_chunks):
            raise ValueError("Exactly four non-empty chunks are required")
        leaves = [Node(data) for data in data_chunks]

        self.root = self.__build_tree_recursive(leaves)
    
    def __build_tree_recursive(self, nodes: list[Node]) -> Node:
        half = len(nodes) // 2

        if len(nodes) == 2:
            return Node(
                nodes[0].data+b'+'+nodes[1].data,    # Duomenys
                hash=calculate_sha256(bytes.fromhex(nodes[0].hash) + bytes.fromhex(nodes[1].hash)),
                left=nodes[0],
                right=nodes[1]
            )
        
        # If there are more than two nodes, split into two halves and build recursively
        left: Node = self.__build_tree_recursive(nodes[:half])
        right: Node = self.__build_tree_recursive(nodes[half:])
        data = left.data+b'+'+right.data

        return Node(data, hash=calculate_sha256(bytes.fromhex(left.hash) + bytes.fromhex(right.hash)), left=left, right=right)

    def printTree(self):
        self.__print_tree_rec(self.root)

    def __print_tree_rec(self, node: Node):
        if node is None:
            return
        print(f'Node data: {node.data}, Hash: {node.hash}')
        self.__print_tree_rec(node.l)
        self.__print_tree_rec(node.r)

def create_manifest(merkle_tree: MerkleTree, data, chunk_count, data_chunks):
    if chunk_count != 4 or len(data_chunks) != 4:
        raise ValueError("Exactly four chunks are required")
    manifest = {
        "firmware_version": "1.0.0",
        "firmware_size": len(data),
        "chunk_count": chunk_count,
        "merkle_root": merkle_tree.root.hash,
        "chunks": [
            {
                "index": i,
                "filename": f"chunk_{i}.bin",
            } for i in range(chunk_count)
        ]
    }
    return manifest
