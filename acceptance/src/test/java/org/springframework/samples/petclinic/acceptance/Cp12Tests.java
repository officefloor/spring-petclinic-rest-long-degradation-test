package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp12: city title-cased on create; reused spelling if the city already exists. */
@Tag("cp12")
class Cp12Tests extends AcceptanceBase {

	@Test
	void coreTitleCasesCity() throws Exception {
		int s = seq();
		ObjectNode o = ownerNode();
		o.put("city", "riverdale" + s); // lowercase input
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.city").value("Riverdale" + s));
	}

	@Test
	void functionalityReusesExistingCitySpelling() throws Exception {
		int s = seq();
		String city = "greenvale" + s;
		ObjectNode a = ownerNode();
		a.put("city", city);
		String stored = fetchOwner(createOwnerOk(a)).get("city").asText();

		ObjectNode b = ownerNode();
		b.put("city", city.toUpperCase()); // same city, different case -> reuse A's spelling
		assertEquals(stored, fetchOwner(createOwnerOk(b)).get("city").asText());
	}
}
