import paho.mqtt.publish as publish
import file_prepare
import base64
import json

host = "localhost"

manifest_message = {'topic': "ota/pi5/manifest", 'payload': "", 'qos': 1, 'retain': False}

if __name__ == "__main__":
    # Get the manifest and chunks
    data = file_prepare.read_file(file_prepare.file_name)
    chunk_count = 4  # Number of chunks to split the data into
    data_chunks = file_prepare.split_data(data, chunk_count)

    for i, chunk in enumerate(data_chunks):
        with open(f"chunk_{i}.bin", "wb") as f:
            f.write(chunk)

    merkle_tree = file_prepare.MerkleTree(data_chunks)

    manifest = file_prepare.create_manifest(merkle_tree, data, chunk_count, data_chunks)

    with open("manifest.json", "w") as f:
        json.dump(manifest, f, indent=4)

    # Update the payloads for the MQTT messages
    manifest_message['payload'] = json.dumps(manifest).encode('utf-8')
    chunk_payloads = []
    for i, chunk in enumerate(data_chunks):
        chunk_payloads.append(
            {
                "firmware_version": manifest["firmware_version"],
                "chunk_index": i,
                "chunk_data": base64.b64encode(chunk).decode('utf-8')  # Encode the chunk data in base64 for transmission
            }
        )
    
    messages = [manifest_message]  # Start with the manifest message

    for payload in chunk_payloads:
        messages.append(
            {
                'topic': "ota/pi5/chunks",
                'payload': json.dumps(payload).encode('utf-8'),
                'qos': 1,
                'retain': False
            }
        )
    
    publish.multiple(messages, hostname=host)
    

