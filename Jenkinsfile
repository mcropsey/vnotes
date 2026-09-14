pipeline {
    agent any

    environment {
        DEPLOY_HOST = '192.168.1.98'
        DEPLOY_USER = 'mcropsey'
        DEPLOY_PATH = '/home/mcropsey/vnotes'

        // Akamai Active Testing
        ACTIVE_CONFIG_FILE_PATH = '/akamai/active-config.json'
        ACTIVE_REGISTRY_URL = "us-central1-docker.pkg.dev/noname-artifacts/nns-docker"
        ACTIVE_API_URL = "https://michaelc-lab.nonamesec.com/active"
        ACTIVE_BACKEND_URI = "https://michaelc-lab.nonamesec.com/active/backend"
        ENV_ID = credentials('active-env-id')
        TEST_GROUP_ID = credentials('active-test-group-id')
        ACTIVE_REGISTRY_CREDS = credentials('active-registry-creds')
        CORE_CLI_CREDS = credentials('active-core-cli-creds')
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
                script {
                    sh 'docker login ${ACTIVE_REGISTRY_URL} -u ${ACTIVE_REGISTRY_CREDS_USR} -p ${ACTIVE_REGISTRY_CREDS_PSW}'
                    sh '''
                        docker run \
                          -e ACTIVE_CONFIG_FILE_PATH="$ACTIVE_CONFIG_FILE_PATH" \
                          -e ACTIVE_BACKEND_URI="$ACTIVE_BACKEND_URI" \
                          -e CORE_CLI_CLIENT_ID="$CORE_CLI_CREDS_USR" \
                          -e CORE_CLI_CLIENT_SECRET="$CORE_CLI_CREDS_PSW" \
                          -v "$(pwd)/akamai:/akamai" \
                          "$ACTIVE_REGISTRY_URL/active-cli:$(curl -k "$ACTIVE_API_URL/backend/version")" \
                          scan \
                          --api-url="$ACTIVE_API_URL" \
                          --env-id="$ENV_ID" \
                          --test-group-id="$TEST_GROUP_ID" \
                          --app-version="${env.BRANCH_NAME ?: 'main'}" \
                          --verbose
                    '''
                }
            }
        }
    }

    post {
        success {
            echo 'Deployed and scanned successfully.'
        }
        failure {
            echo 'Build/deploy/scan failed — check console output.'
        }
    }
}
