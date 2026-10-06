pipeline {
    agent any

    environment {
        DEPLOY_HOST = '192.168.1.98'
        DEPLOY_USER = 'mcropsey'
        DEPLOY_PATH = '/home/mcropsey/vnotes'

        // Akamai Active Testing — non-secret identifiers
        ACTIVE_REGISTRY_URL  = 'us-central1-docker.pkg.dev/noname-artifacts/nns-docker'
        ACTIVE_REGISTRY_USER = '_json_key_base64'
        ACTIVE_API_URL       = 'https://michaelc-lab.nonamesec.com/active'
        ACTIVE_BACKEND_URI   = 'https://michaelc-lab.nonamesec.com/active/backend'
        ACTIVE_TOKEN_URL     = 'https://michaelc-lab.nonamesec.com/auth/token'
        ENV_ID               = '59dc468f-d1ff-4be4-b02e-6f607c9f03f7'  // Notes -> "Jenkins Notes Integration" (cicd)
        TEST_GROUP_ID        = '892b51de-67cf-4328-beea-3ade61bcdeb2'  // Default API Security Tests

        // Last CLI version confirmed present in GAR. The backend's reported
        // /version can briefly outpace the published image after a backend
        // release (seen with 3.71.0 -> 3.71.7, builds 16-18); fall back to
        // this known-good tag rather than failing the whole pipeline.
        FALLBACK_CLI_VERSION = '3.71.0'

        // This job builds */main only, so env.BRANCH_NAME is null here; GIT_BRANCH
        // resolves to 'origin/main', and the scanner wants the bare branch name.
        APP_VERSION = "${(env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'main').replaceAll('^origin/', '')}"
    }

    options {
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Ship code to Docker host') {
            steps {
                sshagent(credentials: ['vnotes-deploy-ssh']) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${DEPLOY_USER}@${DEPLOY_HOST} 'mkdir -p ${DEPLOY_PATH}'
                        tar czf - --exclude='.git' . | ssh -o StrictHostKeyChecking=no ${DEPLOY_USER}@${DEPLOY_HOST} 'tar xzf - -C ${DEPLOY_PATH}'
                    """
                }
            }
        }

        stage('Build & Deploy') {
            steps {
                sshagent(credentials: ['vnotes-deploy-ssh']) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${DEPLOY_USER}@${DEPLOY_HOST} '
                          cd ${DEPLOY_PATH} && \
                          docker compose build && \
                          docker compose up -d
                        '
                    """
                }
            }
        }

        stage('Active Scan') {
            steps {
                withCredentials([
                    string(credentialsId: 'active-registry-key',  variable: 'ACTIVE_REGISTRY_PASSWORD'),
                    string(credentialsId: 'active-cli-client-id', variable: 'SA_CLIENT_ID'),
                    string(credentialsId: 'active-cli-secret',    variable: 'SA_CLIENT_SECRET'),
                ]) {
                    // Leading shebang stops Jenkins injecting `-x`, so the minted
                    // bearer token is never echoed to the console log.
                    sh '''#!/bin/bash
                        set -euo pipefail

                        # Resolve the CLI version; fail loudly rather than building a bad image tag.
                        CLI_VERSION="$(curl -fsS --max-time 30 "$ACTIVE_BACKEND_URI/version" | tr -d '[:space:]')"
                        case "$CLI_VERSION" in
                            ''|*[!0-9.]*) echo "Unexpected /version response: '$CLI_VERSION'"; exit 1 ;;
                        esac
                        echo "Using active-cli:$CLI_VERSION"

                        # Exchange the service-account client credentials for a short-lived
                        # API token. The CLI's CORE_CLI_* path only accepts credentials minted
                        # by the CI/CD wizard, but --api-token/ACTIVE_API_TOKEN accepts this.
                        # printf is a shell builtin and curl reads the body from stdin, so the
                        # secrets never appear in the process table.
                        #
                        # No -f here: on failure we want the auth server's error body (which
                        # never contains our secrets, only its own error description) printed
                        # to the log, instead of curl silently swallowing it.
                        TOKEN_RESPONSE="$(
                            printf '{"grant_type":"client_credentials","client_id":"%s","client_secret":"%s"}' \
                                "$SA_CLIENT_ID" "$SA_CLIENT_SECRET" \
                            | curl -sS --max-time 30 -w '\n%{http_code}' -X POST "$ACTIVE_TOKEN_URL" \
                                -H 'Content-Type: application/json' --data-binary @-
                        )"
                        TOKEN_HTTP_CODE="$(echo "$TOKEN_RESPONSE" | tail -n1)"
                        TOKEN_BODY="$(echo "$TOKEN_RESPONSE" | sed '$d')"
                        if [ "$TOKEN_HTTP_CODE" != "200" ]; then
                            echo "Token request to $ACTIVE_TOKEN_URL failed with HTTP $TOKEN_HTTP_CODE: $TOKEN_BODY" >&2
                            exit 1
                        fi
                        ACTIVE_API_TOKEN="$(echo "$TOKEN_BODY" | sed -n 's/.*"accessToken"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p')"
                        if [ -z "$ACTIVE_API_TOKEN" ]; then
                            echo "Could not find accessToken in response from $ACTIVE_TOKEN_URL: $TOKEN_BODY" >&2
                            exit 1
                        fi
                        export ACTIVE_API_TOKEN
                        echo "Obtained Active Testing API token."

                        mkdir -p "$WORKSPACE/akamai"

                        echo "$ACTIVE_REGISTRY_PASSWORD" \
                          | docker login "$ACTIVE_REGISTRY_URL" -u "$ACTIVE_REGISTRY_USER" --password-stdin

                        # The backend can report a CLI version slightly ahead of what's
                        # actually published to GAR. Try it, and fall back to the last
                        # known-good tag instead of hard-failing the pipeline.
                        ACTIVE_CLI_IMAGE="$ACTIVE_REGISTRY_URL/active-cli:$CLI_VERSION"
                        if ! docker pull "$ACTIVE_CLI_IMAGE"; then
                            echo "WARNING: $ACTIVE_CLI_IMAGE not available in registry yet; falling back to active-cli:$FALLBACK_CLI_VERSION" >&2
                            ACTIVE_CLI_IMAGE="$ACTIVE_REGISTRY_URL/active-cli:$FALLBACK_CLI_VERSION"
                            docker pull "$ACTIVE_CLI_IMAGE"
                        fi

                        docker run --rm \
                          -e ACTIVE_BACKEND_URI \
                          -e ACTIVE_API_TOKEN \
                          -v "$WORKSPACE/akamai:/akamai" \
                          "$ACTIVE_CLI_IMAGE" \
                          scan \
                            --api-url="$ACTIVE_API_URL" \
                            --env-id="$ENV_ID" \
                            --test-group-id="$TEST_GROUP_ID" \
                            --app-version="$APP_VERSION" \
                            --verbose
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'akamai/**', allowEmptyArchive: true
            sh 'docker logout "$ACTIVE_REGISTRY_URL" || true'
        }
        success {
            echo 'Deployed and scanned successfully.'
        }
        failure {
            echo 'Build/deploy/scan failed — check console output.'
        }
    }
}
