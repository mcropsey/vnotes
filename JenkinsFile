pipeline {
    agent any

    environment {
        DEPLOY_HOST = '192.168.1.98'
        DEPLOY_USER = 'mcropsey'
        DEPLOY_PATH = '/home/mcropsey/vnotes'
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
                        rsync -az --delete \
                          -e "ssh -o StrictHostKeyChecking=no" \
                          ./ ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/
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
    }

    post {
        success {
            echo 'Deployed successfully.'
        }
        failure {
            echo 'Build/deploy failed — check console output.'
        }
    }
}
