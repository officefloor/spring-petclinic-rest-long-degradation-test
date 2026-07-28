package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Experimenter-owned, black-box acceptance base for PetClinic-Evolve.
 *
 * <p>These tests drive the REST API of the fully-booted application via
 * {@link MockMvc}, so the Spring @RestController arm and the OfficeFloor
 * YAML-composed-function arm are judged by identical externals. They contain no
 * knowledge of either implementation.
 *
 * <p>Security: the experiment runs with PetClinic security disabled (the repo
 * default). If you enable it, pass -Dpetclinic.test.user=... -Dpetclinic.test.password=...
 * and every request will carry HTTP Basic auth.
 */
@SpringBootTest
@AutoConfigureMockMvc
public abstract class AcceptanceBase {

	private static final AtomicInteger SEQ = new AtomicInteger(0);

	@Autowired
	protected MockMvc mvc;

	@Autowired
	protected ObjectMapper om;

	// --- request builders --------------------------------------------------

	protected MockHttpServletRequestBuilder auth(MockHttpServletRequestBuilder b) {
		String user = System.getProperty("petclinic.test.user");
		if (user == null) {
			return b;
		}
		String pass = System.getProperty("petclinic.test.password", "");
		String token = Base64.getEncoder()
				.encodeToString((user + ":" + pass).getBytes(StandardCharsets.UTF_8));
		return b.header("Authorization", "Basic " + token);
	}

	protected String json(JsonNode node) {
		try {
			return om.writeValueAsString(node);
		}
		catch (Exception e) {
			throw new RuntimeException(e);
		}
	}

	protected ResultActions createOwner(JsonNode body) throws Exception {
		return mvc.perform(auth(post("/api/owners").contentType(MediaType.APPLICATION_JSON)
				.content(json(body))));
	}

	protected int createOwnerOk(JsonNode body) throws Exception {
		return extractId(createOwner(body).andExpect(status().is2xxSuccessful()));
	}

	protected ResultActions getOwner(int id) throws Exception {
		return mvc.perform(auth(get("/api/owners/" + id)));
	}

	protected ResultActions updateOwner(int id, JsonNode body) throws Exception {
		return mvc.perform(auth(put("/api/owners/" + id).contentType(MediaType.APPLICATION_JSON)
				.content(json(body))));
	}

	protected ResultActions addPet(int ownerId, JsonNode pet) throws Exception {
		return mvc.perform(auth(post("/api/owners/" + ownerId + "/pets")
				.contentType(MediaType.APPLICATION_JSON).content(json(pet))));
	}

	protected ResultActions updatePet(int petId, JsonNode pet) throws Exception {
		return mvc.perform(auth(put("/api/pets/" + petId).contentType(MediaType.APPLICATION_JSON)
				.content(json(pet))));
	}

	// --- payload builders ---------------------------------------------------

	/** A fully valid owner (all base fields, a unique telephone). */
	protected ObjectNode validOwner(String firstName, String lastName) {
		ObjectNode o = om.createObjectNode();
		o.put("firstName", firstName);
		o.put("lastName", lastName);
		o.put("address", "123 Test Street");
		o.put("city", "London");
		o.put("telephone", uniquePhone());
		return o;
	}

	protected ObjectNode validOwner() {
		return validOwner("John", "Tester");
	}

	protected ObjectNode validPet(String name) {
		ObjectNode p = om.createObjectNode();
		p.put("name", name);
		p.put("birthDate", "2020-01-01");
		ObjectNode type = om.createObjectNode();
		type.put("id", 1); // seed PetType id 1 exists in PetClinic
		p.set("type", type);
		return p;
	}

	/** A unique 10-digit telephone (61 + 8 digits), safe against seed data. */
	protected String uniquePhone() {
		return String.format("61%08d", SEQ.incrementAndGet());
	}

	protected String uniqueEmail() {
		return "owner" + SEQ.incrementAndGet() + "@example.com";
	}

	protected String today() {
		return LocalDate.now().toString(); // yyyy-MM-dd
	}

	// --- helpers ------------------------------------------------------------

	protected int extractId(ResultActions ra) throws Exception {
		String body = ra.andReturn().getResponse().getContentAsString();
		if (body != null && !body.isBlank()) {
			JsonNode n = om.readTree(body);
			if (n.hasNonNull("id")) {
				return n.get("id").asInt();
			}
		}
		String location = ra.andReturn().getResponse().getHeader("Location");
		if (location != null && location.contains("/")) {
			return Integer.parseInt(location.substring(location.lastIndexOf('/') + 1));
		}
		throw new IllegalStateException("no id in create response: " + body);
	}
}
