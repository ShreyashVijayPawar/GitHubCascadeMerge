# Spring Boot Application

This is a sample Spring Boot application created for testing cascade merge functionality.

## Requirements

- Java 17 or higher
- Maven 3.6+

## Building the Application

```bash
mvn clean package
```

## Running the Application

```bash
mvn spring-boot:run
```

The application will start on `http://localhost:8080/app`

## API Endpoints

- `GET /app/` - Welcome message
- `GET /app/api/hello` - Hello API endpoint
- `GET /app/actuator/health` - Health check endpoint

## Project Structure

```
src/
├── main/
│   ├── java/
│   │   └── com/example/
│   │       ├── SpringBootApplication.java
│   │       └── controller/
│   │           └── HelloController.java
│   └── resources/
│       └── application.properties
└── test/
    └── java/
        └── com/example/
            └── SpringBootApplicationTests.java
```
