package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp17: optional postcode; if present, must match a simple alphanumeric pattern. */
@Tag("cp17")
class Cp17Tests extends AcceptanceBase {

	@Test
	void coreRejectsInvalidPostcode() throws Exception {
		ObjectNode o = validOwner();
		o.put("postcode", "!!bad!!");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsMissingPostcode() throws Exception {
		createOwner(validOwner()).andExpect(status().is2xxSuccessful());
	}

	@Test
	void functionalityStoresValidPostcode() throws Exception {
		ObjectNode o = validOwner();
		o.put("postcode", "AB12CD");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.postcode").value("AB12CD"));
	}
}
