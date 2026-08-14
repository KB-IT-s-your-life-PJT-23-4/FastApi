pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
    }

    environment {
        IMAGE_NAME = 'wosyh18/mirizoom-fastapi'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate') {
            steps {
                sh '''
                    set -eu

                    docker --version
                    test -f Dockerfile
                    test -f pyproject.toml
                    test -f uv.lock
                    test -f tests/test_application.py

                    echo "Repository: ${GIT_URL}"
                    echo "Commit: ${GIT_COMMIT}"
                    echo "Image: ${IMAGE_NAME}:${BUILD_NUMBER}"
                '''
            }
        }

        stage('Build Image') {
            steps {
                sh '''
                    set -eu

                    docker build \
                        --pull \
                        --tag "${IMAGE_NAME}:${BUILD_NUMBER}" \
                        --tag "${IMAGE_NAME}:latest" \
                        .
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    set -eu

                    docker run --rm \
                        --env OPENAI_API_KEY=ci-test-key \
                        --env OPENAI_EMBEDDING_API_KEY=ci-test-key \
                        "${IMAGE_NAME}:${BUILD_NUMBER}" \
                        uv run pytest tests/test_application.py
                '''
            }
        }

        stage('Push Image to Docker Hub') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'dockerhub-credentials',
                        usernameVariable: 'DOCKERHUB_USERNAME',
                        passwordVariable: 'DOCKERHUB_TOKEN'
                    )
                ]) {
                    sh '''
                        set -eu

                        export DOCKER_CONFIG="${WORKSPACE}/.docker"
                        mkdir -p "${DOCKER_CONFIG}"

                        echo "${DOCKERHUB_TOKEN}" |
                            docker login \
                                --username "${DOCKERHUB_USERNAME}" \
                                --password-stdin

                        docker push "${IMAGE_NAME}:${BUILD_NUMBER}"
                        docker push "${IMAGE_NAME}:latest"
                    '''
                }
            }
        }
    }

    post {
        success {
            echo "FastAPI 이미지 Push 완료: ${IMAGE_NAME}:${BUILD_NUMBER}"
        }

        failure {
            echo 'FastAPI 테스트, 이미지 Build 또는 Push에 실패했습니다.'
        }

        always {
            deleteDir()
        }
    }
}
