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
                        ACTIVE_API_TOKEN="$(
                            printf '{"grant_type":"client_credentials","client_id":"%s","client_secret":"%s"}' \
                                "$SA_CLIENT_ID" "$SA_CLIENT_SECRET" \
                            | curl -fsS --max-time 30 -X POST "$ACTIVE_TOKEN_URL" \
                                -H 'Content-Type: application/json' --data-binary @- \
                            | sed -n 's/.*"accessToken"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p'
                        )"
                        if [ -z "$ACTIVE_API_TOKEN" ]; then
                            echo "Failed to obtain an Active Testing API token from $ACTIVE_TOKEN_URL" >&2
                            exit 1
                        fi
                        export ACTIVE_API_TOKEN
                        echo "Obtained Active Testing API token."

                        mkdir -p "$WORKSPACE/akamai"

                        echo "$ACTIVE_REGISTRY_PASSWORD" \
                          | docker login "$ACTIVE_REGISTRY_URL" -u "$ACTIVE_REGISTRY_USER" --password-stdin

                        docker run --rm \
                          -e ACTIVE_BACKEND_URI \
                          -e ACTIVE_API_TOKEN \
                          -v "$WORKSPACE/akamai:/akamai" \
                          "$ACTIVE_REGISTRY_URL/active-cli:$CLI_VERSION" \
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
