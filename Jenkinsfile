// VNotes: deploy to the lab Docker host, then run an Akamai API Security
// Active Testing scan against https://notes.cropseyit.com.
//
// Active Testing tenant: mikec-lab.nonamesec.com
//   App  VNotes      ab930b27-1a22-4acf-b5bf-0add38e87a62
//   Env  Jenkins CI  2f05f900-45ce-4f65-b213-a0838416d548  (type: cicd)
//
// Jenkins credentials used (Manage Jenkins > Credentials > System > Global):
//   vnotes-deploy-ssh          SSH key for the deploy host
//   mikec-at-registry-key      GAR pull key for the active-cli image (_json_key_base64)
//   mikec-at-sa-client-id      mikec-lab service account client id
//   mikec-at-sa-client-secret  mikec-lab service account client secret
//   vnotes-at-users            "user:pass user:pass ..." test users for AT auth refresh

pipeline {
    agent any

    parameters {
        choice(name: 'SEVERITY_THRESHOLD', choices: ['high', 'medium', 'low', 'info', 'none'],
               description: 'Minimum finding severity that gates the build (findings at/above this mark the build UNSTABLE)')
        booleanParam(name: 'SKIP_DEPLOY', defaultValue: false,
                     description: 'Skip ship/build/deploy and only run the Active Testing scan')
    }

    environment {
        DEPLOY_HOST = '192.168.1.98'
        DEPLOY_USER = 'mcropsey'
        DEPLOY_PATH = '/home/mcropsey/vnotes'
        TARGET_URL  = 'https://notes.cropseyit.com'

        // Akamai Active Testing (mikec-lab) -- non-secret identifiers
        AT_BASE              = 'https://mikec-lab.nonamesec.com'
        ACTIVE_API_URL       = 'https://mikec-lab.nonamesec.com/active'
        ACTIVE_BACKEND_URI   = 'https://mikec-lab.nonamesec.com/active/backend'
        ACTIVE_TOKEN_URL     = 'https://mikec-lab.nonamesec.com/auth/token'
        ACTIVE_REGISTRY_URL  = 'us-central1-docker.pkg.dev/noname-artifacts/nns-docker'
        ACTIVE_REGISTRY_USER = '_json_key_base64'
        APP_ID               = 'ab930b27-1a22-4acf-b5bf-0add38e87a62'  // VNotes
        ENV_ID               = '2f05f900-45ce-4f65-b213-a0838416d548'  // VNotes -> "Jenkins CI" (cicd)
        TEST_GROUP_ID        = '892b51de-67cf-4328-beea-3ade61bcdeb2'  // Default API Security Tests

        // Job builds */main only, so BRANCH_NAME is null; GIT_BRANCH is 'origin/main'.
        // params are undefined on the first run after the parameters block is added; default them.
        SEVERITY_GATE = "${params.SEVERITY_THRESHOLD ?: 'high'}"

        APP_VERSION = "${(env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'main').replaceAll('^origin/', '')}"
    }

    options {
        timeout(time: 60, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Ship code to Docker host') {
            when { expression { !(params.SKIP_DEPLOY ?: false) } }
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
            when { expression { !(params.SKIP_DEPLOY ?: false) } }
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

        stage('Wait for app') {
            steps {
                sh 'curl -fsS --retry 20 --retry-delay 3 --retry-all-errors --max-time 10 "$TARGET_URL/health"'
            }
        }

        stage('Active Scan') {
            steps {
                withCredentials([
                    string(credentialsId: 'mikec-at-registry-key',     variable: 'ACTIVE_REGISTRY_PASSWORD'),
                    string(credentialsId: 'mikec-at-sa-client-id',     variable: 'SA_CLIENT_ID'),
                    string(credentialsId: 'mikec-at-sa-client-secret', variable: 'SA_CLIENT_SECRET'),
                    string(credentialsId: 'vnotes-at-users',           variable: 'AT_USERS'),
                ]) {
                    script {
                        // Shebang stops Jenkins adding `-x`, so tokens are never echoed.
                        def rc = sh(returnStatus: true, script: '''#!/bin/bash
                            set -euo pipefail

                            # 1. Service-account client credentials -> short-lived platform token.
                            #    The CLI accepts it via ACTIVE_API_TOKEN, and it also authorizes the
                            #    AT REST API used to refresh the test-user auths below.
                            TOKEN_BODY="$(printf '{"grant_type":"client_credentials","client_id":"%s","client_secret":"%s"}' \
                                    "$SA_CLIENT_ID" "$SA_CLIENT_SECRET" \
                                | curl -sS --max-time 30 -X POST "$ACTIVE_TOKEN_URL" \
                                    -H 'Content-Type: application/json' --data-binary @-)"
                            ACTIVE_API_TOKEN="$(echo "$TOKEN_BODY" | sed -n 's/.*"accessToken"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p')"
                            if [ -z "$ACTIVE_API_TOKEN" ]; then
                                echo "Could not obtain accessToken from $ACTIVE_TOKEN_URL: $TOKEN_BODY" >&2
                                exit 2
                            fi
                            export ACTIVE_API_TOKEN
                            echo "Obtained Active Testing API token."

                            # 2. VNotes JWTs expire after 24h: re-login each test user and push fresh
                            #    Bearer tokens into the AT environment's authentications.
                            AT_TOKEN="$ACTIVE_API_TOKEN" ./akamai/refresh-auths.sh || exit 2

                            # 3. Pull the active-cli image matching the backend version.
                            CLI_VERSION="$(curl -fsS --max-time 30 "$ACTIVE_BACKEND_URI/version" | tr -d '[:space:]')"
                            case "$CLI_VERSION" in
                                ''|*[!0-9.]*) echo "Unexpected /version response: '$CLI_VERSION'" >&2; exit 2 ;;
                            esac
                            echo "Using active-cli:$CLI_VERSION"
                            # Log in against the registry HOST, not the repo path, or docker pull
                            # won't find the stored credential.
                            echo "$ACTIVE_REGISTRY_PASSWORD" \
                              | docker login "https://${ACTIVE_REGISTRY_URL%%/*}" -u "$ACTIVE_REGISTRY_USER" --password-stdin
                            ACTIVE_CLI_IMAGE="$ACTIVE_REGISTRY_URL/active-cli:$CLI_VERSION"
                            docker pull -q "$ACTIVE_CLI_IMAGE" || exit 2

                            # 4. Scan. Exit code is non-zero if the run errors OR findings exceed
                            #    the severity threshold; tee the log so we can tell which.
                            mkdir -p "$WORKSPACE/akamai/results"
                            set +e
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
                                --severity-threshold="$SEVERITY_GATE" \
                                --verbose 2>&1 | tee "$WORKSPACE/akamai/results/scan.log"
                            SCAN_RC=${PIPESTATUS[0]}
                            set -e

                            if [ "$SCAN_RC" -ne 0 ] && grep -q 'Exceeded severity threshold' "$WORKSPACE/akamai/results/scan.log"; then
                                exit 3   # scan completed; findings at/above threshold
                            fi
                            exit "$SCAN_RC"
                        ''')

                        if (rc == 3) {
                            unstable("Active Testing found issues at/above '${env.SEVERITY_GATE}' severity -- see ${env.AT_BASE}/active/applications/${env.APP_ID}")
                        } else if (rc != 0) {
                            error("Active Testing scan failed to run (exit ${rc})")
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'akamai/results/**', allowEmptyArchive: true
            sh 'docker logout "https://${ACTIVE_REGISTRY_URL%%/*}" || true'
        }
        success  { echo 'Deployed and scanned: no findings at/above threshold.' }
        unstable { echo 'Deployed and scanned: findings at/above threshold (expected for the vulnerable variant).' }
        failure  { echo 'Build/deploy/scan failed -- check console output.' }
    }
}
