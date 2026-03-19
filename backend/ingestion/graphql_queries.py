"""Sui GraphQL query templates for chain data enrichment.

Separated from graphql_client.py for maintainability.
See Econmartin's jotunn.lol API reference for schema documentation.
"""

GET_OBJECT_WITH_DYNFIELDS = """
query GetObject($address: SuiAddress!) {
  object(address: $address) {
    address
    version
    asMoveObject {
      contents {
        type { repr }
        json
      }
      dynamicFields {
        nodes {
          name { json type { repr } }
          value {
            ... on MoveValue {
              json
            }
          }
        }
      }
    }
  }
}
"""

GET_EVENTS_BY_MODULE = """
query GetEvents($module: String!, $first: Int, $after: String) {
  events(filter: { module: $module }, first: $first, after: $after) {
    nodes {
      contents {
        json
        type { repr }
      }
      timestamp
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_CHARACTER_OBJECTS = """
query GetCharacters($type: String!, $first: Int, $after: String) {
  objects(
    first: $first,
    after: $after,
    filter: { type: $type }
  ) {
    nodes {
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_OBJECT_VERSIONS = """
query GetObjectVersions($address: SuiAddress!, $first: Int) {
  objectVersions(address: $address, first: $first) {
    nodes {
      version
      digest
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage }
  }
}
"""

GET_OWNED_OBJECTS = """
query GetOwnedObjects($owner: SuiAddress!, $first: Int, $after: String) {
  objects(filter: { owner: $owner }, first: $first, after: $after) {
    nodes {
      address
      version
      asMoveObject {
        contents {
          json
          type { repr }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_TRANSACTIONS = """
query GetTransactions($address: SuiAddress!, $first: Int, $after: String) {
  transactions(filter: { affectedAddress: $address }, first: $first, after: $after) {
    nodes {
      digest
      effects {
        status
        timestamp
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

GET_KILLMAIL_OBJECTS = """
query GetKillmailObjects($type: String!, $first: Int, $after: String) {
  objects(
    first: $first,
    after: $after,
    filter: { type: $type }
  ) {
    nodes {
      address
      version
      asMoveObject {
        contents { json }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""
