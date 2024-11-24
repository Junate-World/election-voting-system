from flask import Flask, jsonify, request, render_template
from blockchain import VotingBlockchain
from uuid import uuid4
from flask_socketio import SocketIO, emit

# Instantiate the Node
app = Flask(__name__)
# Initialize SocketIO
socketio = SocketIO(app)

# Generate a unique address for this node
node_identifier = str(uuid4()).replace("-", "")

# Instantiate the Blockchain
blockchain = VotingBlockchain()

@app.route('/')
def index():
    return render_template('index.html')  # Render the HTML file

# Add a unique identifier for each node when generating the nonce
@app.route('/mine', methods=['GET'])
def mine():
    last_proof = blockchain.last_block["proof"]
    nonce = int(uuid4().int)  # A unique starting point for each node
    proof = None
    increment = 1  # Increment the nonce

    while not proof:
        candidate_proof = last_proof + nonce  # Incorporate unique nonce
        if blockchain.valid_proof(last_proof, candidate_proof, nonce):
            proof = candidate_proof
        nonce += increment  # Increment nonce

    blockchain.new_transaction(sender="0", recipient=node_identifier, amount=1)
    previous_hash = blockchain.hash(blockchain.last_block)
    block = blockchain.new_block(proof, previous_hash, nonce)

    response = {
        "message": "New Block Forged",
        "index": block["index"],
        "transactions": block["transactions"],
        "proof": block["proof"],
        "previous_hash": block["previous_hash"],
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    required = ["sender", "recipient", "amount"]
    if not all(k in values for k in required):
        return "Missing values", 400

    index = blockchain.new_transaction(
        values["sender"], values["recipient"], values["amount"]
    )
    response = {"message": f"Transaction will be added to Block {index}"}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        "chain": blockchain.chain,
        "length": len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get("nodes")
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400
    for node in nodes:
        blockchain.register_node(node)

    print(f"Registered nodes: {blockchain.nodes}")
    
    response = {
        "message": "New nodes have been added",
        "total_nodes": list(blockchain.nodes),
    }
    

    return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        print("Chain was replaced with a longer chain")
    else:
        print("No conflict detected, chain remains the same")
        
    response = {
        "message": "Our chain was replaced" if replaced else "Our chain is authoritative",
        "chain": blockchain.chain,
    }
    return jsonify(response), 200

#@app.route('/register_voter', methods=['POST'])
#def register_voter():
    values = request.get_json()
    voter_id = values.get("voter_id")
    if not voter_id:
        return jsonify({"error": "Voter ID is required"}), 400

    success = blockchain.register_voter(voter_id)
    if success:
        return jsonify({"message": f"Voter {voter_id} registered successfully"}), 201
    else:
        return jsonify({"message": f"Voter {voter_id} is already registered"}), 400
  

@app.route('/register/voter', methods=['POST'])
def register_voter():
    values = request.get_json()
    voter_id = values.get("voter_id")
    if not voter_id:
        return jsonify({"error": "Missing voter_id"}), 400

    voter_token = blockchain.register_voter(voter_id)
    if voter_token:
        response = {
            "message": f"Voter {voter_id} registered successfully.",
            "token": voter_token,
        }
        return jsonify(response), 201
    else:
        return jsonify({"message": f"Voter {voter_id} is already registered."}), 400


@app.route('/add/candidate', methods=['POST'])
def add_candidate():
    values = request.get_json()
    candidate_name = values.get("candidate_name")
    if not candidate_name:
        return jsonify({"error": "Missing candidate_name"}), 400

    if blockchain.add_candidate(candidate_name):
        response = {"message": f"Candidate {candidate_name} added successfully."}
        return jsonify(response), 201
    else:
        return jsonify({"message": f"Candidate {candidate_name} already exists."}), 400

@app.route('/start_election', methods=['POST'])
def start_election():
    blockchain.start_election()
    return jsonify({"message": "Election has started"}), 200

@app.route('/vote', methods=['POST'])
def cast_vote():
    values = request.get_json()

    # Validate payload
    voter_id = values.get("voter_id")
    token = values.get("token")
    candidate_name = values.get("candidate_name")

    if not voter_id or not token or not candidate_name:
        return jsonify({"error": "Missing voter_id, token, or candidate_name"}), 400

    # Check if voter is registered
    if voter_id not in blockchain.voters:
        return jsonify({"error": "Voter not registered."}), 404

    # Validate token
    if blockchain.voters[voter_id] != token:
        return jsonify({"error": "Invalid token."}), 403

    # Check if candidate exists
    if candidate_name not in blockchain.candidates:
        return jsonify({"error": "Candidate does not exist."}), 404

    # Add the vote as a transaction
    blockchain.new_transaction(
        sender=voter_id, 
        recipient=candidate_name, 
        amount=1  # One vote represents "1"
    )

    # Invalidate the token
    blockchain.voters[voter_id] = None

    response = {
        "message": f"Vote cast successfully for {candidate_name}.",
        "voter_id": voter_id,
        "candidate_name": candidate_name,
    }

    socketio.emit('update_tally', tally_votes())
    return jsonify(response), 201



@app.route('/end_election', methods=['POST'])
def end_election():
    blockchain.end_election()
    return jsonify({"message": "Election has ended"}), 200

@app.route('/get_voters', methods=['GET'])
def get_voters():
    return jsonify({"voters": list(blockchain.voters)}), 200


@app.route('/tally', methods=['GET'])
def tally_votes():
    vote_count = {candidate: 0 for candidate in blockchain.candidates}

    for block in blockchain.chain:
        print(f"Processing block {block['index']}: {block['transactions']}")
        for transaction in block["transactions"]:
            recipient = transaction["recipient"]
            if recipient in vote_count:
                vote_count[recipient] += 1

    response = {
        "status": "success",
        "results": vote_count
    }
    socketio.emit('update_tally', vote_count)
    return jsonify(response), 200



if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
